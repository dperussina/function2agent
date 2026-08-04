package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Stage 7 — re-origination (T091, OD-12).
//
// The proxy makes its OWN outbound TLS connection to the pinned address with ordinary certificate
// validation, injecting the operator's target credential. No CA enters the sandbox and no
// certificate pin is asked of the operator.
//
// NO TLS INTERCEPTION. NO RESPONSE-BODY REWRITING. Rewriting absolute URLs out of responses would
// apply a content transformation to untrusted bytes on the enforcement path, creating a new
// injection surface at the one component every other safety property depends on. It is rejected,
// not deferred, and the body below is copied with io.Copy and nothing else.

// Dialer is the outbound connection dependency, injectable so that tests can substitute a stub.
// There is no test flag anywhere in this file: production and test differ only in which value is
// assigned to this field.
type Dialer interface {
	DialContext(ctx context.Context, network, addr string) (net.Conn, error)
}

// errResolverDisabled is returned by the dialer's resolver. FR-016 forbids re-resolving names per
// request; wiring a resolver that always fails means an accidental resolution is a loud failure
// rather than a silent second destination.
var errResolverDisabled = errors.New("reoriginate: name resolution is disabled (FR-016)")

// PinnedDialer dials exactly one address, always, and never consults a resolver.
type PinnedDialer struct {
	// Addr is the pinned ip:port from F2A_PROXY_UPSTREAM_ADDR.
	Addr string

	inner *net.Dialer
}

// NewPinnedDialer builds a dialer locked to addr.
func NewPinnedDialer(addr string, timeout time.Duration) *PinnedDialer {
	return &PinnedDialer{
		Addr: addr,
		inner: &net.Dialer{
			Timeout: timeout,
			Resolver: &net.Resolver{
				PreferGo: true,
				Dial: func(context.Context, string, string) (net.Conn, error) {
					return nil, errResolverDisabled
				},
			},
		},
	}
}

// DialContext ignores the address the transport asked for and dials the pinned one. The address is
// re-checked against the denied classes here, on the value the kernel will receive, rather than
// only on the value the operator typed (FR-017).
func (d *PinnedDialer) DialContext(ctx context.Context, network, _ string) (net.Conn, error) {
	if err := checkDialAddress(d.Addr); err != nil {
		return nil, err
	}
	if network != "tcp" && network != "tcp4" && network != "tcp6" {
		return nil, fmt.Errorf("reoriginate: refusing network %q", network)
	}
	return d.inner.DialContext(ctx, network, d.Addr)
}

// tierGuardError is stage 7's own refusal to send a call that is not read_only. It is
// defence in depth: stages 5 and 6 have already decided this, and stage 7 checks it again on the
// value it is about to act on so that removing either of them does not put a write on the wire.
type tierGuardError struct{ Tier string }

func (e *tierGuardError) Error() string { return "reoriginate: refusing tier " + e.Tier }

// hop-by-hop headers, which are meaningful only on one connection and must not be forwarded.
var hopByHop = []string{
	"Connection", "Keep-Alive", "Proxy-Authenticate", "Proxy-Authorization",
	"Proxy-Connection", "Te", "Trailer", "Transfer-Encoding", "Upgrade",
}

// Reoriginator is stage 7.
type Reoriginator struct {
	stageName

	origin           PinnedOrigin
	credentialHeader string
	credential       Secret
	client           *http.Client
}

// ReoriginatorConfig is what stage 7 needs.
type ReoriginatorConfig struct {
	Origin           PinnedOrigin
	CredentialHeader string
	Credential       Secret
	Dialer           Dialer

	// RootCAs supplies additional trust anchors. Nil means the host's system roots, which is
	// what production uses. It is a configuration value, not a test flag: no code below
	// branches on whether it is set.
	RootCAs *x509.CertPool

	Timeout time.Duration
}

// NewReoriginator builds stage 7.
func NewReoriginator(cfg ReoriginatorConfig) *Reoriginator {
	timeout := cfg.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	transport := &http.Transport{
		DialContext: cfg.Dialer.DialContext,
		TLSClientConfig: &tls.Config{
			// Ordinary certificate validation. InsecureSkipVerify is never set, and the name
			// validated is the pinned origin's, not whatever the request-target said.
			ServerName: cfg.Origin.Host,
			RootCAs:    cfg.RootCAs,
			MinVersion: tls.VersionTLS12,
		},
		ForceAttemptHTTP2:     false,
		TLSHandshakeTimeout:   timeout,
		ResponseHeaderTimeout: timeout,
		MaxIdleConns:          8,
		IdleConnTimeout:       60 * time.Second,
	}
	return &Reoriginator{
		stageName:        "reoriginate",
		origin:           cfg.Origin,
		credentialHeader: cfg.CredentialHeader,
		credential:       cfg.Credential,
		client: &http.Client{
			Transport: transport,
			Timeout:   timeout,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				// A redirect is a new destination chosen by the target. Following it would
				// take the decision away from the pipeline, so it is returned to the agent
				// as a response instead.
				return http.ErrUseLastResponse
			},
		},
	}
}

// Deliver re-originates the request and copies the response back verbatim.
func (s *Reoriginator) Deliver(ctx context.Context, w http.ResponseWriter, rc *requestContext) error {
	if rc.Tier != tierReadOnly {
		return &tierGuardError{Tier: rc.Tier}
	}

	outURL := &url.URL{
		Scheme:   s.origin.Scheme,
		Host:     s.origin.HostPort(),
		Path:     rc.Path,
		RawQuery: rc.Query,
	}

	var body io.Reader
	if rc.Request != nil && rc.Request.Body != nil {
		body = rc.Request.Body
	}
	out, err := http.NewRequestWithContext(ctx, rc.Method, outURL.String(), body)
	if err != nil {
		return fmt.Errorf("reoriginate: cannot build upstream request: %w", err)
	}
	out.Header = sanitisedOutboundHeader(rc.Header, s.credentialHeader)
	out.Host = s.origin.Host
	if rc.Request != nil {
		out.ContentLength = rc.Request.ContentLength
	}

	// The credential is read here and nowhere else. It is never placed on rc, never on a
	// decision record, and never in an error.
	out.Header.Set(s.credentialHeader, s.credential.Reveal())

	resp, err := s.client.Do(out)
	if err != nil {
		return fmt.Errorf("reoriginate: upstream request failed: %w", redactURLError(err))
	}
	defer resp.Body.Close()

	dst := w.Header()
	for k, vs := range resp.Header {
		if isHopByHop(k) {
			continue
		}
		for _, v := range vs {
			dst.Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	// Verbatim. No rewriting of any kind.
	_, _ = io.Copy(w, resp.Body)
	return nil
}

// sanitisedOutboundHeader copies the inbound headers, dropping hop-by-hop fields, the capability
// header and any pre-existing credential header. Stripping the capability header keeps the
// session handle inside the enforcement boundary; stripping the credential header stops the agent
// from choosing what the proxy authenticates as.
func sanitisedOutboundHeader(in http.Header, credentialHeader string) http.Header {
	out := make(http.Header, len(in))
	blocked := map[string]bool{
		http.CanonicalHeaderKey(capabilityHeader): true,
	}
	if credentialHeader != "" {
		blocked[http.CanonicalHeaderKey(credentialHeader)] = true
	}
	for _, h := range hopByHop {
		blocked[http.CanonicalHeaderKey(h)] = true
	}
	// Headers named by Connection are hop-by-hop for this connection too.
	for _, c := range in[http.CanonicalHeaderKey("Connection")] {
		for _, tok := range strings.Split(c, ",") {
			if t := strings.TrimSpace(tok); t != "" {
				blocked[http.CanonicalHeaderKey(t)] = true
			}
		}
	}
	for k, vs := range in {
		if blocked[http.CanonicalHeaderKey(k)] {
			continue
		}
		for _, v := range vs {
			out.Add(k, v)
		}
	}
	return out
}

func isHopByHop(key string) bool {
	ck := http.CanonicalHeaderKey(key)
	for _, h := range hopByHop {
		if http.CanonicalHeaderKey(h) == ck {
			return true
		}
	}
	return false
}

// redactURLError strips the URL from a *url.Error before it reaches a log or a response body. The
// URL cannot contain the credential — the credential travels in a header — but the query string it
// carries is attacker-influenceable, and an error path is not the place to find out.
func redactURLError(err error) error {
	var ue *url.Error
	if errors.As(err, &ue) {
		return fmt.Errorf("%s upstream: %w", ue.Op, ue.Err)
	}
	return err
}
