package main

import (
	"bytes"
	"context"
	"net"
	"net/http"
	"strings"
	"sync"
)

// Stage 2 — form (T085, FR-018).
//
// CONNECT denied. Any Upgrade denied. Non-HTTP bytes refused. Ambiguous framing REJECTED OUTRIGHT
// RATHER THAN NORMALIZED: normalizing is what lets the enforcement point and the target disagree
// about what the request is, and a disagreement about the method and path defeats FR-018 entirely.
//
// WHY THIS STAGE PARSES THE RAW REQUEST HEAD ITSELF.
//
// Go's net/http server is strict about several framing ambiguities and rejects them with a 400 or
// a 501 before a handler is entered. It is NOT strict about all of them, and measured on Go 1.24.3
// it NORMALISES three of the cases in this component's corpus rather than refusing them:
//
//   - Content-Length together with Transfer-Encoding: chunked is ACCEPTED. net/http deletes the
//     Content-Length field, frames the body as chunked, and — on a keep-alive connection — then
//     parses whatever follows the terminating chunk as a second pipelined request. That is the
//     CL.TE desync, delivered to the handler as two ordinary requests.
//   - Two identical Content-Length fields are collapsed into one.
//   - obs-fold header continuation is accepted and folded into a single space.
//
// In all three the handler sees an already-normalised request and cannot tell. A check written
// against r.Header would therefore be a check that cannot fire. So stage 2 reads the raw bytes of
// the request head off the connection and parses them itself, and it additionally asserts that its
// own reading of the method and request-target agrees with net/http's — a disagreement between two
// parsers on the same bytes being the exact failure Q-01 buys a second language against.
//
// The enforcement point also runs with keep-alives disabled and with net/http's built-in
// `OPTIONS *` handler disabled; see NewEnforcementServer.

// maxRawHead bounds the recorded head. A head larger than this is refused rather than truncated
// and interpreted.
const maxRawHead = 32 << 10

type rawHeadCtxKey struct{}

// rawHeadRecorder wraps a connection and records the bytes of its first request head, up to and
// including the terminating CRLFCRLF. Recording stops there: no body byte is ever retained.
type rawHeadRecorder struct {
	net.Conn

	mu       sync.Mutex
	buf      []byte
	complete bool
	overflow bool
	stopped  bool
}

func newRawHeadRecorder(c net.Conn) *rawHeadRecorder {
	return &rawHeadRecorder{Conn: c, buf: make([]byte, 0, 1024)}
}

func (c *rawHeadRecorder) Read(p []byte) (int, error) {
	n, err := c.Conn.Read(p)
	if n > 0 {
		c.mu.Lock()
		if !c.stopped {
			c.buf = append(c.buf, p[:n]...)
			if i := bytes.Index(c.buf, []byte("\r\n\r\n")); i >= 0 {
				c.buf = c.buf[:i+4]
				c.complete = true
				c.stopped = true
			} else if len(c.buf) > maxRawHead {
				c.overflow = true
				c.stopped = true
			}
		}
		c.mu.Unlock()
	}
	return n, err
}

// Head returns the recorded request head and whether it is complete and within bounds.
func (c *rawHeadRecorder) Head() ([]byte, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.complete || c.overflow {
		return nil, false
	}
	out := make([]byte, len(c.buf))
	copy(out, c.buf)
	return out, true
}

// recordingListener returns connections that record their first request head.
type recordingListener struct{ net.Listener }

func (l recordingListener) Accept() (net.Conn, error) {
	c, err := l.Listener.Accept()
	if err != nil {
		return nil, err
	}
	return newRawHeadRecorder(c), nil
}

// rawField is one header field exactly as it appeared on the wire: the name before the first
// colon, and everything after it, untrimmed.
type rawField struct {
	Name  string
	Value string
}

// rawHead is this component's own parse of the request head.
type rawHead struct {
	Method    string
	Target    string
	Version   string
	Fields    []rawField
	ObsFold   bool
	Malformed string
}

// parseRawHead parses the bytes of a request head strictly. Anything it will not parse is
// Malformed, and a malformed head is refused rather than repaired.
func parseRawHead(b []byte) rawHead {
	var h rawHead
	if len(b) == 0 {
		h.Malformed = "empty_head"
		return h
	}
	if bytes.IndexByte(b, 0) >= 0 {
		h.Malformed = "nul_byte_in_head"
		return h
	}
	body := bytes.TrimSuffix(b, []byte("\r\n\r\n"))
	lines := bytes.Split(body, []byte("\r\n"))
	for _, ln := range lines {
		// A bare LF inside what should be a CRLF-delimited line is a line terminator one
		// parser honours and another does not. Refused.
		if bytes.IndexByte(ln, '\n') >= 0 || bytes.IndexByte(ln, '\r') >= 0 {
			h.Malformed = "bare_cr_or_lf_in_line"
			return h
		}
	}
	if len(lines) == 0 {
		h.Malformed = "no_request_line"
		return h
	}

	parts := strings.Split(string(lines[0]), " ")
	if len(parts) != 3 {
		h.Malformed = "request_line_not_three_tokens"
		return h
	}
	h.Method, h.Target, h.Version = parts[0], parts[1], parts[2]

	for _, raw := range lines[1:] {
		ln := string(raw)
		if ln == "" {
			continue
		}
		if ln[0] == ' ' || ln[0] == '\t' {
			h.ObsFold = true
			continue
		}
		i := strings.IndexByte(ln, ':')
		if i < 0 {
			h.Malformed = "header_line_without_colon"
			return h
		}
		name := ln[:i]
		if !isHTTPToken(name) {
			// Covers "Foo : v" (space before the colon), which some parsers accept as the
			// field "Foo" and others reject.
			h.Malformed = "header_name_not_a_token"
			return h
		}
		h.Fields = append(h.Fields, rawField{Name: name, Value: ln[i+1:]})
	}
	return h
}

// valuesOf returns every raw value for name, case-insensitively, in wire order.
func (h rawHead) valuesOf(name string) []string {
	var out []string
	for _, f := range h.Fields {
		if strings.EqualFold(f.Name, name) {
			out = append(out, f.Value)
		}
	}
	return out
}

// formInput is stage 2's input: this component's own parse of the head, plus what net/http made
// of the same bytes, so the two can be compared.
type formInput struct {
	// From net/http.
	method     string
	target     string
	protoMajor int
	protoMinor int

	parsedTransferEncoding []string
	parsedContentLength    []string
	upgrade                []string
	connection             []string
	headerNames            []string
	headerValues           []string

	// From this component's own parse of the raw head.
	rawHeadAvailable bool
	raw              rawHead
}

func formInputFrom(rc *requestContext) formInput {
	names := make([]string, 0, len(rc.Header))
	values := make([]string, 0, len(rc.Header))
	for k, vs := range rc.Header {
		names = append(names, k)
		values = append(values, vs...)
	}
	fi := formInput{
		method:                 rc.Method,
		target:                 rc.RawTarget,
		protoMajor:             rc.ProtoMajor,
		protoMinor:             rc.ProtoMinor,
		parsedTransferEncoding: rc.TransferEncoding,
		parsedContentLength:    headerValues(rc.Header, "Content-Length"),
		upgrade:                headerValues(rc.Header, "Upgrade"),
		connection:             headerValues(rc.Header, "Connection"),
		headerNames:            names,
		headerValues:           values,
		rawHeadAvailable:       rc.RawHeadAvailable,
		raw:                    rc.RawHead,
	}
	return fi
}

// rawHeadFrom pulls the recorded head out of a request's context and parses it.
func rawHeadFrom(ctx context.Context) (rawHead, bool) {
	rec, ok := ctx.Value(rawHeadCtxKey{}).(*rawHeadRecorder)
	if !ok || rec == nil {
		return rawHead{}, false
	}
	b, ok := rec.Head()
	if !ok {
		return rawHead{}, false
	}
	return parseRawHead(b), true
}

// FormStage is stage 2.
type FormStage struct {
	stageName
}

// NewFormStage builds stage 2.
func NewFormStage() *FormStage { return &FormStage{stageName: "form"} }

// Evaluate applies checkForm to the request.
func (s *FormStage) Evaluate(_ context.Context, rc *requestContext) (stageResult, error) {
	return checkForm(formInputFrom(rc)), nil
}

// checkForm is the whole of stage 2, as a pure function so the framing corpus can drive it
// directly with values net/http would have normalised away.
func checkForm(fi formInput) stageResult {
	if strings.EqualFold(fi.method, http.MethodConnect) {
		// CONNECT is denied outright. It is also why a CONNECT-oriented proxy was rejected:
		// such a proxy sees a host and a port and silently degrades a method allowlist into a
		// destination one (OD-12).
		return denyResult(RuleConnectDenied, "method="+quoteForDetail(sanitizeDetail(fi.method)))
	}

	if len(fi.upgrade) > 0 || len(fi.raw.valuesOf("Upgrade")) > 0 {
		return denyResult(RuleUpgradeDenied, "header=\"Upgrade\"")
	}
	connectionValues := append(append([]string{}, fi.connection...), fi.raw.valuesOf("Connection")...)
	for _, c := range connectionValues {
		for _, tok := range strings.Split(c, ",") {
			if strings.EqualFold(strings.TrimSpace(tok), "upgrade") {
				return denyResult(RuleUpgradeDenied, "header=\"Connection: upgrade\"")
			}
		}
	}

	// Non-HTTP bytes have nothing to speak to. A wholly non-HTTP byte stream never becomes an
	// *http.Request — Go's server rejects it on the wire and closes the connection. What
	// reaches here is the near-miss: a protocol version this cleartext HTTP/1 listener does not
	// speak (an h2c preface arrives as method PRI over HTTP/2.0), an invalid method token, or a
	// header field name that is not a token.
	if fi.protoMajor != 1 || (fi.protoMinor != 0 && fi.protoMinor != 1) {
		return denyResult(RuleNonHTTPBytes, sanitizeDetail("proto=\"HTTP/"+itoa(fi.protoMajor)+"."+itoa(fi.protoMinor)+"\""))
	}
	if !isHTTPToken(fi.method) {
		return denyResult(RuleNonHTTPBytes, "reason=\"method_not_a_token\"")
	}
	for _, n := range fi.headerNames {
		if !isHTTPToken(n) {
			return denyResult(RuleNonHTTPBytes, "reason=\"header_name_not_a_token\"")
		}
	}
	for _, v := range fi.headerValues {
		if strings.ContainsAny(v, "\r\n\x00") {
			return denyResult(RuleNonHTTPBytes, "reason=\"control_character_in_header_value\"")
		}
	}

	// Without the raw head this stage cannot see what net/http normalised, so it cannot make
	// the guarantee FR-018 asks for. It refuses rather than making a weaker one.
	if !fi.rawHeadAvailable {
		return denyResult(RuleNonHTTPBytes, "reason=\"raw_request_head_unavailable\"")
	}
	if fi.raw.Malformed != "" {
		return denyResult(RuleNonHTTPBytes, "reason="+quoteForDetail(sanitizeDetail(fi.raw.Malformed)))
	}
	if fi.raw.Version != "HTTP/1.1" && fi.raw.Version != "HTTP/1.0" {
		return denyResult(RuleNonHTTPBytes, "raw_version="+quoteForDetail(sanitizeDetail(fi.raw.Version)))
	}
	// Two parsers, same bytes, different answer about the method or the request-target. This is
	// the parser differential itself, and there is no safe way to proceed from it.
	if fi.raw.Method != fi.method || fi.raw.Target != fi.target {
		return denyResult(RuleNonHTTPBytes, "reason=\"parser_differential_on_request_line\"")
	}

	return checkFraming(fi)
}

// checkFraming rejects every request whose length is not stated exactly once and unambiguously.
// Nothing here normalises: each of these is a refusal.
func checkFraming(fi formInput) stageResult {
	// obs-fold. RFC 9112 deprecates it and requires an intermediary either to reject the
	// message or to replace the fold with a space. Replacing is normalising, so this rejects:
	// a folded Content-Length is read by one parser as the folded value and by another as the
	// first line alone.
	if fi.raw.ObsFold {
		return denyResult(RuleAmbiguousFraming, "reason=\"obs_fold_header_continuation\"")
	}

	rawCL := fi.raw.valuesOf("Content-Length")
	rawTE := fi.raw.valuesOf("Transfer-Encoding")

	hasTE := len(rawTE) > 0 || len(fi.parsedTransferEncoding) > 0
	hasCL := len(rawCL) > 0 || len(fi.parsedContentLength) > 0

	// Both Content-Length and Transfer-Encoding. This is the CL.TE / TE.CL smuggling primitive:
	// two parsers pick different fields and disagree about where the request ends. net/http
	// resolves it in favour of chunked; this refuses it.
	if hasTE && hasCL {
		return denyResult(RuleAmbiguousFraming, "reason=\"content_length_and_transfer_encoding\"")
	}

	// Multiple Content-Length fields. Refused whether or not the values agree: de-duplicating
	// identical values is still normalisation, and it is the step that lets a downstream parser
	// with a different de-duplication rule see a different message.
	if len(rawCL) > 1 || len(fi.parsedContentLength) > 1 {
		return denyResult(RuleAmbiguousFraming, "reason=\"multiple_content_length\"")
	}
	for _, v := range append(append([]string{}, rawCL...), fi.parsedContentLength...) {
		if strings.Contains(v, ",") {
			// "Content-Length: 5, 5" is a list, and a list is two claims.
			return denyResult(RuleAmbiguousFraming, "reason=\"content_length_list\"")
		}
		if !isCanonicalContentLength(v) {
			// A leading '+', a trailing space, a sign, a hex prefix: every one of these is
			// read differently by different parsers.
			return denyResult(RuleAmbiguousFraming, "reason=\"content_length_not_canonical\"")
		}
	}

	// Transfer-Encoding must be exactly one field whose value is exactly "chunked".
	// "chunked, identity", "identity, chunked", "chunked;q=1" and a repeated field are all
	// refused rather than reduced to their final coding.
	if len(rawTE) > 1 || len(fi.parsedTransferEncoding) > 1 {
		return denyResult(RuleAmbiguousFraming, "reason=\"multiple_transfer_encoding\"")
	}
	for _, v := range rawTE {
		if !exactlyChunked(v) {
			return denyResult(RuleAmbiguousFraming, "reason=\"transfer_encoding_not_exactly_chunked\"")
		}
	}
	for _, v := range fi.parsedTransferEncoding {
		if !exactlyChunked(v) {
			return denyResult(RuleAmbiguousFraming, "reason=\"transfer_encoding_not_exactly_chunked\"")
		}
	}

	return allowResult()
}

func exactlyChunked(v string) bool {
	return strings.EqualFold(stripLeadingOWS(v), "chunked")
}

// isCanonicalContentLength accepts a single leading run of OWS (the field-value delimiter) followed
// by 1*DIGIT and nothing else: no sign, no trailing whitespace, no underscores, no hex.
//
// Trailing OWS is legal HTTP and this refuses it anyway. That is deliberate and it is the strict
// reading of "rejected outright rather than normalized": trimming a trailing space off a length is
// a normalisation, and the corpus names whitespace in a Content-Length as a case to reject.
func isCanonicalContentLength(v string) bool {
	s := stripLeadingOWS(v)
	if s == "" || len(s) > 19 {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

func stripLeadingOWS(s string) string {
	i := 0
	for i < len(s) && (s[i] == ' ' || s[i] == '\t') {
		i++
	}
	return s[i:]
}

// tokenChars is RFC 9110's tchar set.
const tokenChars = "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

func isHTTPToken(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if !strings.ContainsRune(tokenChars, rune(s[i])) {
			return false
		}
	}
	return true
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
