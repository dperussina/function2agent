package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"sort"
	"strings"
	"time"
)

// T083 — the enforcement point.
//
// A cleartext listener presented to the agent as the target's base URL, in front of an
// origin-validating TLS client to one pinned upstream (OD-12, T-05). The sandbox has exactly one
// reachable address, needs no resolver and holds no trust anchor.
//
// CONFIGURATION IS REQUIRED ENVIRONMENT VARIABLES WITH NO DEFAULT FOR ANY OF THEM. A default here
// would be a policy nobody reviewed (FR-012), on the component every other safety property depends
// on. A missing key is named and the process starts nothing.

const (
	envListen           = "F2A_PROXY_LISTEN"
	envUpstreamOrigin   = "F2A_PROXY_UPSTREAM_ORIGIN"
	envUpstreamAddr     = "F2A_PROXY_UPSTREAM_ADDR"
	envPolicy           = "F2A_PROXY_POLICY"
	envSessionDB        = "F2A_PROXY_SESSION_DB"
	envDecisionDB       = "F2A_PROXY_DECISION_DB"
	envCredentialHeader = "F2A_TARGET_CREDENTIAL_HEADER"
	envCredential       = "F2A_TARGET_CREDENTIAL"
)

// requiredEnv is every key, in the order they are reported when missing.
var requiredEnv = []string{
	envListen, envUpstreamOrigin, envUpstreamAddr, envPolicy,
	envSessionDB, envDecisionDB, envCredentialHeader, envCredential,
}

// redactionMarker is what a credential renders as, everywhere, always.
const redactionMarker = "[REDACTED]"

// Secret holds a credential value in a type that cannot be printed.
//
// String, GoString and MarshalJSON all return the redaction marker, so %v, %s, %+v, %#v, %q and
// encoding/json all render it redacted — including when it is a field of a larger struct, because
// fmt calls a field's Stringer. The value is reachable only through Reveal, which has exactly one
// caller: the header injection in stage 7.
type Secret struct {
	v string
}

// NewSecret wraps a credential value.
func NewSecret(v string) Secret { return Secret{v: v} }

// String returns the redaction marker.
func (s Secret) String() string { return redactionMarker }

// GoString returns the redaction marker, so %#v is redacted too.
func (s Secret) GoString() string { return redactionMarker }

// MarshalJSON returns the redaction marker.
func (s Secret) MarshalJSON() ([]byte, error) { return []byte(`"` + redactionMarker + `"`), nil }

// Reveal returns the credential value. Every call site is a place a credential leaves the type.
func (s Secret) Reveal() string { return s.v }

// Empty reports whether no credential was supplied.
func (s Secret) Empty() bool { return s.v == "" }

// Fingerprint is a truncated SHA-256 of the credential, for records that must identify WHICH
// credential was used. Truncated so that it is an identifier and not an offline-checkable digest
// of a short secret.
func (s Secret) Fingerprint() string {
	if s.v == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(s.v))
	return "sha256:" + hex.EncodeToString(sum[:])[:12]
}

// Config is the validated startup configuration. TargetCredential is an exported field of type
// Secret so that fmt calls Secret.String on it; an unexported field would be printed structurally
// and would leak.
type Config struct {
	Listen           string
	UpstreamOrigin   PinnedOrigin
	UpstreamAddr     string
	PolicyPath       string
	SessionDBPath    string
	DecisionDBPath   string
	CredentialHeader string
	TargetCredential Secret

	// AddressExemption is derived from UpstreamAddr by validatePinnedAddr and is never read
	// from configuration. There is no environment variable that sets it: an operator can move
	// the exemption only by moving the declared target, which is the property that keeps it
	// from becoming a toggle (FR-017, owner decision 2026-08-03).
	AddressExemption pinnedExemption
}

// String keeps a whole-struct print safe even if a future field is added carelessly.
func (c Config) String() string {
	return fmt.Sprintf("Config{Listen:%s UpstreamOrigin:%s UpstreamAddr:%s Policy:%s SessionDB:%s DecisionDB:%s CredentialHeader:%s TargetCredential:%s}",
		c.Listen, c.UpstreamOrigin.URLBase(), c.UpstreamAddr, c.PolicyPath, c.SessionDBPath,
		c.DecisionDBPath, c.CredentialHeader, redactionMarker)
}

// LoadConfig reads and validates every required key from getenv. Every failure is fatal.
func LoadConfig(getenv func(string) string) (Config, error) {
	var missing []string
	vals := map[string]string{}
	for _, k := range requiredEnv {
		v := getenv(k)
		if strings.TrimSpace(v) == "" {
			missing = append(missing, k)
			continue
		}
		vals[k] = v
	}
	if len(missing) > 0 {
		sort.Strings(missing)
		return Config{}, fmt.Errorf(
			"config: required environment variable(s) not set and there is no default for any of them: %s",
			strings.Join(missing, ", "))
	}

	cfg := Config{
		Listen:           strings.TrimSpace(vals[envListen]),
		UpstreamAddr:     strings.TrimSpace(vals[envUpstreamAddr]),
		PolicyPath:       vals[envPolicy],
		SessionDBPath:    vals[envSessionDB],
		DecisionDBPath:   vals[envDecisionDB],
		CredentialHeader: strings.TrimSpace(vals[envCredentialHeader]),
		// Never trimmed: a credential's bytes are its bytes.
		TargetCredential: NewSecret(vals[envCredential]),
	}

	origin, err := parsePinnedOrigin(vals[envUpstreamOrigin])
	if err != nil {
		return Config{}, err
	}
	cfg.UpstreamOrigin = origin

	if _, _, err := net.SplitHostPort(cfg.Listen); err != nil {
		return Config{}, fmt.Errorf("config: %s=%q is not a valid host:port: %w", envListen, cfg.Listen, err)
	}

	// FR-016: the pinned address is a literal ip:port fixed at configuration time. FR-017: it
	// must not be in a denied class. Checked here so a proxy pinned into a denied class does
	// not start, and again in the dialer on the address actually dialled.
	exempt, err := validatePinnedAddr(cfg.UpstreamAddr)
	if err != nil {
		return Config{}, err
	}
	cfg.AddressExemption = exempt

	if !isHTTPToken(cfg.CredentialHeader) {
		return Config{}, fmt.Errorf("config: %s=%q is not a valid HTTP header field name", envCredentialHeader, cfg.CredentialHeader)
	}
	if strings.EqualFold(cfg.CredentialHeader, capabilityHeader) {
		return Config{}, fmt.Errorf("config: %s must not be %s", envCredentialHeader, capabilityHeader)
	}
	// The error above and every other error in this function name keys and never values of the
	// credential; there is a test asserting the credential appears in none of them.

	return cfg, nil
}

func parsePinnedOrigin(raw string) (PinnedOrigin, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return PinnedOrigin{}, fmt.Errorf("config: %s=%q is not a URL: %w", envUpstreamOrigin, raw, err)
	}
	if u.Scheme != "https" {
		// The proxy originates TLS with ordinary certificate validation (OD-12). A cleartext
		// upstream is not a posture this component offers.
		return PinnedOrigin{}, fmt.Errorf("config: %s=%q must use scheme https", envUpstreamOrigin, raw)
	}
	if u.User != nil {
		return PinnedOrigin{}, fmt.Errorf("config: %s must not contain userinfo", envUpstreamOrigin)
	}
	if u.Path != "" && u.Path != "/" {
		return PinnedOrigin{}, fmt.Errorf("config: %s=%q must be an origin with no path", envUpstreamOrigin, raw)
	}
	if u.RawQuery != "" || u.Fragment != "" {
		return PinnedOrigin{}, fmt.Errorf("config: %s=%q must be an origin with no query or fragment", envUpstreamOrigin, raw)
	}
	host, port, err := net.SplitHostPort(u.Host)
	if err != nil || host == "" || port == "" {
		// FR-016 pins at host-AND-port granularity, so the port is explicit. A scheme default
		// would be this component choosing a destination the operator did not write down.
		return PinnedOrigin{}, fmt.Errorf(
			"config: %s=%q must be scheme://host:port with an explicit port (FR-016 pins at host-and-port granularity)",
			envUpstreamOrigin, raw)
	}
	return PinnedOrigin{Scheme: "https", Host: host, Port: port}, nil
}

// validatePinnedAddr checks the declared upstream and returns the one exemption this process will
// honour for it (FR-017, owner decision 2026-08-03).
//
// The exemption is derived HERE, from the declared address, and nowhere else. It is returned
// rather than stored in a package variable so that every consumer has to be handed it explicitly.
func validatePinnedAddr(addr string) (pinnedExemption, error) {
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		return noExemption, fmt.Errorf("config: %s=%q is not a valid ip:port: %w", envUpstreamAddr, addr, err)
	}
	parsed, err := netip.ParseAddr(host)
	if err != nil {
		return noExemption, fmt.Errorf(
			"config: %s=%q must contain a literal IP address; names are never resolved (FR-016)",
			envUpstreamAddr, addr)
	}
	if port == "" {
		return noExemption, fmt.Errorf("config: %s=%q must contain a port (FR-016)", envUpstreamAddr, addr)
	}

	// Build the exemption first. For a public origin this is empty; for an RFC1918 origin it
	// names that one address; for link-local, the metadata service, loopback or unique-local it
	// is an error, and the proxy does not start.
	exempt, err := exemptionForPinnedOrigin(parsed)
	if err != nil {
		return noExemption, fmt.Errorf("config: %s=%q rejected: %w", envUpstreamAddr, addr, err)
	}
	if err := checkDialAddress(addr, exempt); err != nil {
		return noExemption, fmt.Errorf("config: %s=%q rejected: %w", envUpstreamAddr, addr, err)
	}
	return exempt, nil
}

// Proxy is the assembled enforcement point.
type Proxy struct {
	Config   Config
	Policy   *Policy
	Handler  http.Handler
	sessions *SessionStore
	log      *DecisionLog
}

// Close releases the databases.
func (p *Proxy) Close() error {
	var first error
	if p.sessions != nil {
		if err := p.sessions.Close(); err != nil && first == nil {
			first = err
		}
	}
	if p.log != nil {
		if err := p.log.Close(); err != nil && first == nil {
			first = err
		}
	}
	return first
}

// BuildProxy assembles the seven stages from a validated configuration.
func BuildProxy(cfg Config) (*Proxy, error) {
	policy, err := LoadPolicy(cfg.PolicyPath)
	if err != nil {
		return nil, err
	}
	sessions, err := OpenSessionStore(cfg.SessionDBPath)
	if err != nil {
		return nil, err
	}
	decisions, err := OpenDecisionLog(cfg.DecisionDBPath)
	if err != nil {
		sessions.Close()
		return nil, err
	}

	final := NewReoriginator(ReoriginatorConfig{
		Origin:           cfg.UpstreamOrigin,
		CredentialHeader: cfg.CredentialHeader,
		Credential:       cfg.TargetCredential,
		Dialer:           NewPinnedDialer(cfg.UpstreamAddr, cfg.AddressExemption, 15*time.Second),
	})

	pipeline := NewPipeline(
		defaultStages(cfg.UpstreamOrigin, policy, sessions, nil),
		final,
		decisions,
		policy,
		cfg.TargetCredential.Fingerprint(),
	)

	return &Proxy{
		Config:   cfg,
		Policy:   policy,
		Handler:  pipeline,
		sessions: sessions,
		log:      decisions,
	}, nil
}

// defaultStages is the registered order of the six gate stages. Stage 7 is not in this list: it is
// not a gate and the sequencer cannot reach it by iterating.
func defaultStages(origin PinnedOrigin, policy *Policy, sessions SessionLookup, now Clock) []Stage {
	return []Stage{
		NewCapabilityStage(sessions, now), // 1
		NewFormStage(),                    // 2
		NewDestinationStage(origin),       // 3
		NewMethodStage(origin, policy),    // 4
		NewEffectStage(policy),            // 5
		NewUnresolvableStage(),            // 6
	}
}

// NewEnforcementServer builds the cleartext listener the agent is handed as the target's base URL.
//
// Three settings here are load-bearing rather than tuning:
//
//   - ConnContext hands each request the raw-head recorder installed by ServeEnforcement's
//     listener wrapper, which is what lets stage 2 see the bytes net/http normalised.
//   - DisableGeneralOptionsHandler, because net/http otherwise answers "OPTIONS *" itself with a
//     200 and the pipeline never runs. Asterisk-form must reach stage 3 to be denied.
//   - SetKeepAlivesEnabled(false), applied by ServeEnforcement: one request per connection. It
//     costs connection reuse and it makes request smuggling by pipelining structurally impossible
//     — bytes following the first request are never parsed as a second one.
func NewEnforcementServer(cfg Config, handler http.Handler, logger *log.Logger) *http.Server {
	srv := &http.Server{
		Addr:                         cfg.Listen,
		Handler:                      handler,
		DisableGeneralOptionsHandler: true,
		ReadHeaderTimeout:            10 * time.Second,
		ReadTimeout:                  30 * time.Second,
		WriteTimeout:                 60 * time.Second,
		IdleTimeout:                  60 * time.Second,
		MaxHeaderBytes:               maxRawHead,
		ErrorLog:                     logger,
		ConnContext: func(ctx context.Context, c net.Conn) context.Context {
			if rec, ok := c.(*rawHeadRecorder); ok {
				return context.WithValue(ctx, rawHeadCtxKey{}, rec)
			}
			return ctx
		},
	}
	srv.SetKeepAlivesEnabled(false)
	return srv
}

// ServeEnforcement listens on cfg.Listen and serves, with the raw-head recording listener.
func ServeEnforcement(srv *http.Server) error {
	ln, err := net.Listen("tcp", srv.Addr)
	if err != nil {
		return err
	}
	return srv.Serve(recordingListener{ln})
}

func main() {
	logger := log.New(os.Stderr, "f2a-proxy: ", log.LstdFlags|log.LUTC)

	cfg, err := LoadConfig(os.Getenv)
	if err != nil {
		logger.Fatalf("startup refused: %v", err)
	}
	proxy, err := BuildProxy(cfg)
	if err != nil {
		logger.Fatalf("startup refused: %v", err)
	}
	defer proxy.Close()

	srv := NewEnforcementServer(cfg, proxy.Handler, logger)

	logger.Printf("listening on %s, pinned upstream %s at %s, policy version %s",
		cfg.Listen, cfg.UpstreamOrigin.URLBase(), cfg.UpstreamAddr, proxy.Policy.PolicyVersion)

	if err := ServeEnforcement(srv); err != nil {
		logger.Fatalf("server stopped: %v", err)
	}
}
