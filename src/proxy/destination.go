package main

import (
	"context"
	"net"
	"net/url"
	"strings"
	"sync/atomic"
)

// Stage 3 — destination (T086, T-09, Q-07).
//
// Accepted: an origin-form request-target ("/orders/1"), and an absolute-form http:// target whose
// host:port equals the pinned origin's host:port — which is how a URL echoed out of a response
// body still works (T-09 part 2).
//
// Denied: absolute-form https://, with the named reason absolute_https_denied AND A COUNTER.
// The counter is not decoration. Making absolute https work requires either terminating TLS in the
// sandbox or rewriting response bodies, and OD-12 rejected both; Q-07 says that if this reason
// dominates real traffic that is evidence for revisiting the posture in v2. The counter is the
// instrument that makes the question answerable, so it is exposed on every decision record and
// through a package-level accessor.
//
// Also denied: authority-form ("api.example.com:443", the CONNECT shape), asterisk-form ("*"), and
// an absolute-form target naming any other host.

// absoluteHTTPSDenied is the Q-07 instrument. Monotonic for the life of the process.
var absoluteHTTPSDenied atomic.Uint64

// AbsoluteHTTPSDeniedCount returns the number of absolute-form https request-targets denied since
// start. Package-level so the decision log, an operator endpoint and the test suite read the same
// number.
func AbsoluteHTTPSDeniedCount() uint64 { return absoluteHTTPSDenied.Load() }

// resetAbsoluteHTTPSDeniedCount exists for tests, which must be able to assert an increment rather
// than a running total. No production code calls it.
func resetAbsoluteHTTPSDeniedCount() { absoluteHTTPSDenied.Store(0) }

// PinnedOrigin is the one legitimate destination, as configured. FR-016 pins at host-and-port
// granularity at configuration time; nothing here is ever re-resolved.
type PinnedOrigin struct {
	Scheme string // always "https": the proxy originates TLS
	Host   string // host only, no port
	Port   string // explicit port, never a scheme default
}

// HostPort is the pinned authority.
func (o PinnedOrigin) HostPort() string { return net.JoinHostPort(o.Host, o.Port) }

// URLBase is the origin as a URL prefix, used when re-originating.
func (o PinnedOrigin) URLBase() string { return o.Scheme + "://" + o.HostPort() }

// DestinationStage is stage 3.
type DestinationStage struct {
	stageName
	origin PinnedOrigin
}

// NewDestinationStage builds stage 3.
func NewDestinationStage(origin PinnedOrigin) *DestinationStage {
	return &DestinationStage{stageName: "destination", origin: origin}
}

// Evaluate classifies the request-target.
func (s *DestinationStage) Evaluate(_ context.Context, rc *requestContext) (stageResult, error) {
	return checkDestination(rc.RawTarget, s.origin), nil
}

// checkDestination is stage 3 as a pure function over the raw request-target.
func checkDestination(rawTarget string, origin PinnedOrigin) stageResult {
	if rawTarget == "" {
		return denyResult(RuleRequestTargetFormUnsupported, "form=\"empty\"")
	}
	if rawTarget == "*" {
		// Asterisk-form. Only meaningful for a server-wide OPTIONS, which this enforcement
		// point does not proxy: there is no operation in the served set it could resolve to.
		return denyResult(RuleRequestTargetFormUnsupported, "form=\"asterisk\"")
	}
	if strings.HasPrefix(rawTarget, "/") {
		// Origin-form. Accepted; the path is resolved by stages 4 to 6.
		if strings.HasPrefix(rawTarget, "//") {
			// "//evil.example.com/x" is a scheme-relative reference, which some parsers read
			// as an authority. Refused rather than disambiguated.
			return denyResult(RuleRequestTargetFormUnsupported, "form=\"protocol_relative\"")
		}
		return allowResult()
	}

	if !strings.Contains(rawTarget, "://") {
		// No leading slash and no scheme separator: authority-form ("api.example.com:443",
		// the CONNECT shape, which url.Parse would otherwise read as scheme "api.example.com"),
		// or garbage.
		return denyResult(RuleRequestTargetFormUnsupported, "form=\"authority_or_unparseable\"")
	}
	u, err := url.ParseRequestURI(rawTarget)
	if err != nil || u.Scheme == "" {
		return denyResult(RuleRequestTargetFormUnsupported, "form=\"absolute_unparseable\"")
	}

	scheme := strings.ToLower(u.Scheme)
	if scheme == "https" {
		// T-09 part 3, and the Q-07 instrument.
		absoluteHTTPSDenied.Add(1)
		return denyResult(RuleAbsoluteHTTPSDenied,
			joinDetail("form=\"absolute\"", "scheme=\"https\"", "count="+itoa64(absoluteHTTPSDenied.Load())))
	}
	if scheme != "http" {
		return denyResult(RuleDestinationNotAllowed, "scheme="+quoteForDetail(sanitizeDetail(scheme)))
	}
	if u.User != nil {
		// Userinfo in a request-target is a credential-shaped value in a place nothing should
		// read one from, and it changes what the authority is for some parsers.
		return denyResult(RuleRequestTargetFormUnsupported, "form=\"absolute_with_userinfo\"")
	}

	host, port := splitHostPortDefault(u.Host, "80")
	if host == "" {
		return denyResult(RuleRequestTargetFormUnsupported, "form=\"absolute_without_host\"")
	}
	// STRICT READING: host AND port must both equal the pinned origin's. FR-016 pins at
	// host-and-port granularity, so an absolute-form target naming the right host on a
	// different port is a different destination.
	if !strings.EqualFold(host, origin.Host) || port != origin.Port {
		return denyResult(RuleDestinationNotAllowed,
			joinDetail("form=\"absolute\"", "authority="+quoteForDetail(sanitizeDetail(net.JoinHostPort(host, port)))))
	}
	return allowResult()
}

// splitHostPortDefault splits an authority, supplying def when no port is present.
func splitHostPortDefault(authority, def string) (host, port string) {
	if authority == "" {
		return "", ""
	}
	h, p, err := net.SplitHostPort(authority)
	if err != nil {
		return strings.Trim(authority, "[]"), def
	}
	return h, p
}

func itoa64(n uint64) string {
	if n == 0 {
		return "0"
	}
	var buf [24]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}
