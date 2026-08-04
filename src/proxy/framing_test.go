package main

import (
	"strings"
	"testing"
)

// T094 — the framing-ambiguity corpus.
//
// A parser differential at the single enforcement point is a complete defeat of FR-018 and is the
// named failure Q-01 buys a second language against. This file has two arms and both are needed:
//
//	ARM A drives checkForm directly with the raw request head. It proves THIS COMPONENT rejects
//	each case, including the cases net/http would have normalised away before a handler could see
//	them. Remove the check and arm A fails.
//
//	ARM B sends the same bytes down a real socket to a real enforcement point and asserts the
//	request never reaches the pinned upstream. It also RECORDS WHICH LAYER REJECTED — net/http's
//	server or this component's stage 2 — because for several of these it is net/http, and claiming
//	stage 2 caught them would be false.
//
// MEASURED ON go1.24.3. net/http's behaviour on these inputs is a property of a dependency and
// the arm-B expectations are pinned to what was actually observed, not to what is desirable.

// rejector names the layer that refused a request.
type rejector string

const (
	byGoServer  rejector = "net/http server (before stage 2)"
	byPipeline  rejector = "this component's pipeline"
	notRejected rejector = "not rejected"
)

// rawFormInput models what stage 2 sees for a set of raw head bytes: this component's own parse,
// and net/http's parsed view emptied out, which is the worst case — net/http has already
// normalised the ambiguity away and stage 2 is the only thing left that can see it.
func rawFormInput(t *testing.T, head string) formInput {
	t.Helper()
	parsed := parseRawHead([]byte(head))
	fi := formInput{
		method:           parsed.Method,
		target:           parsed.Target,
		protoMajor:       1,
		protoMinor:       1,
		rawHeadAvailable: true,
		raw:              parsed,
	}
	if parsed.Version == "HTTP/1.0" {
		fi.protoMinor = 0
	}
	return fi
}

type framingCase struct {
	name string
	// head is the raw request head, always CRLF-terminated with a blank line.
	head string
	// extra is anything written after the head (a body, or a smuggled request).
	extra string
	// wantRule is the rule stage 2 produces for this head in arm A. Empty means arm A expects
	// an allow.
	wantRule string
	// wantRejectedByOnTheWire is which layer refuses it in arm B, as measured on go1.24.3.
	wantRejectedByOnTheWire rejector
	// note records, per case, what net/http does with these bytes.
	note string
}

func framingCorpus() []framingCase {
	cap := "X-F2A-Capability: " + testHandle + "\r\n"
	return []framingCase{
		{
			name:                    "content_length_and_transfer_encoding_with_smuggled_request",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n",
			extra:                   "0\r\n\r\nGET /smuggled HTTP/1.1\r\nHost: api.example.com\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byPipeline,
			note: "net/http ACCEPTS this. It deletes Content-Length, frames the body as chunked, and on a " +
				"keep-alive connection parses the trailing bytes as a second pipelined request — the CL.TE " +
				"desync delivered as two ordinary handler calls. Stage 2 rejects it from the raw head, and " +
				"keep-alives are disabled so the smuggled request is never parsed at all.",
		},
		{
			name:                    "two_conflicting_content_length",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: 0\r\nContent-Length: 5\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byGoServer,
			note:                    "net/http rejects this with 400 before stage 2 runs. Stage 2 implements it anyway and arm A proves it.",
		},
		{
			name:                    "two_identical_content_length",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: 0\r\nContent-Length: 0\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byPipeline,
			note:                    "net/http ACCEPTS this and collapses the two fields into one. Stage 2 refuses the repetition.",
		},
		{
			name:                    "transfer_encoding_chunked_identity",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Transfer-Encoding: chunked, identity\r\n\r\n",
			extra:                   "0\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byGoServer,
			note:                    "net/http rejects this with 501 before stage 2 runs.",
		},
		{
			name:                    "duplicate_transfer_encoding",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n",
			extra:                   "0\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byGoServer,
			note:                    "net/http rejects this with 501 before stage 2 runs.",
		},
		{
			name:                    "obs_fold_header_continuation",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "X-Note: first\r\n\tsecond\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byPipeline,
			note: "net/http ACCEPTS obs-fold on an ordinary header and folds the continuation into the " +
				"previous value with a space. Stage 2 rejects the fold itself, before it can matter which " +
				"header was folded.",
		},
		{
			name:                    "obs_fold_inside_content_length",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: 0\r\n 5\r\n\r\n",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byGoServer,
			note: "net/http folds this to Content-Length: \"0 5\", fails to parse it as a length and rejects " +
				"with 400 before stage 2 runs. Stage 2 rejects it too, on the fold, and arm A proves it.",
		},
		{
			name:                    "content_length_leading_plus",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: +5\r\n\r\n",
			extra:                   "hello",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byGoServer,
			note:                    "net/http rejects this with 400 before stage 2 runs.",
		},
		{
			name:                    "content_length_trailing_whitespace",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: 5 \r\n\r\n",
			extra:                   "hello",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byPipeline,
			note: "net/http ACCEPTS this and trims the value to \"5\". Trailing OWS is legal HTTP; stage 2 " +
				"refuses it anyway, because trimming is a normalisation and the contract says reject rather " +
				"than normalise. Deliberately stricter than the RFC.",
		},
		{
			name:                    "content_length_list",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length: 5, 5\r\n\r\n",
			extra:                   "hello",
			wantRule:                RuleAmbiguousFraming,
			wantRejectedByOnTheWire: byGoServer,
			note:                    "net/http rejects this with 400 before stage 2 runs.",
		},
		{
			name:                    "header_name_with_trailing_space_before_colon",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Content-Length : 5\r\n\r\n",
			extra:                   "hello",
			wantRule:                RuleNonHTTPBytes,
			wantRejectedByOnTheWire: byGoServer,
			note:                    "net/http rejects this with 400 before stage 2 runs.",
		},
		{
			name:                    "connect",
			head:                    "CONNECT api.example.com:443 HTTP/1.1\r\nHost: api.example.com:443\r\n" + cap + "\r\n",
			wantRule:                RuleConnectDenied,
			wantRejectedByOnTheWire: byPipeline,
			note:                    "net/http passes CONNECT to the handler. Stage 2 denies it.",
		},
		{
			name:                    "upgrade",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n",
			wantRule:                RuleUpgradeDenied,
			wantRejectedByOnTheWire: byPipeline,
			note:                    "net/http passes this to the handler. Stage 2 denies it.",
		},
		{
			name:                    "well_formed_control",
			head:                    "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\n" + cap + "\r\n",
			wantRule:                "",
			wantRejectedByOnTheWire: notRejected,
			note:                    "The control. If this is rejected the corpus proves nothing.",
		},
	}
}

// ---------------------------------------------------------------------------
// ARM A — stage 2 rejects each case from the raw head
// ---------------------------------------------------------------------------

func TestFramingCorpusStageTwo(t *testing.T) {
	for _, tc := range framingCorpus() {
		t.Run(tc.name, func(t *testing.T) {
			t.Log("net/http behaviour: " + tc.note)
			got := checkForm(rawFormInput(t, tc.head))
			if tc.wantRule == "" {
				assertResult(t, got, true, RuleAllowed)
				return
			}
			assertResult(t, got, false, tc.wantRule)
		})
	}
}

// TestRawHeadUnavailableIsRefused proves stage 2 does not silently skip the raw-head checks when
// the head could not be recorded. Without this the mechanism would fail open on any connection the
// recorder missed.
func TestRawHeadUnavailableIsRefused(t *testing.T) {
	fi := formInput{method: "GET", target: "/orders/1", protoMajor: 1, protoMinor: 1, rawHeadAvailable: false}
	assertResult(t, checkForm(fi), false, RuleNonHTTPBytes)
}

// TestParserDifferentialOnRequestLineIsRefused covers the case the whole corpus exists for: this
// component and net/http reading the same bytes and disagreeing about the method or the target.
func TestParserDifferentialOnRequestLineIsRefused(t *testing.T) {
	head := "GET /orders/1 HTTP/1.1\r\nHost: h\r\n\r\n"
	fi := rawFormInput(t, head)
	fi.target = "/orders/2" // as if net/http had read a different target
	assertResult(t, checkForm(fi), false, RuleNonHTTPBytes)

	fi2 := rawFormInput(t, head)
	fi2.method = "POST"
	assertResult(t, checkForm(fi2), false, RuleNonHTTPBytes)
}

func TestNonHTTPProtocolVersionRefused(t *testing.T) {
	// An h2c prior-knowledge preface arrives as PRI * HTTP/2.0.
	fi := formInput{method: "PRI", target: "*", protoMajor: 2, protoMinor: 0, rawHeadAvailable: true}
	assertResult(t, checkForm(fi), false, RuleNonHTTPBytes)
}

func TestMalformedRawHeadsRefused(t *testing.T) {
	cases := map[string]string{
		"bare_lf_line_ending":  "GET /orders/1 HTTP/1.1\r\nHost: h\nX-Evil: 1\r\n\r\n",
		"nul_in_head":          "GET /orders/1 HTTP/1.1\r\nHost: h\x00x\r\n\r\n",
		"no_colon_in_header":   "GET /orders/1 HTTP/1.1\r\nHost h\r\n\r\n",
		"request_line_tokens":  "GET /orders/1\r\nHost: h\r\n\r\n",
		"unknown_http_version": "GET /orders/1 HTTP/0.9\r\nHost: h\r\n\r\n",
	}
	for name, head := range cases {
		t.Run(name, func(t *testing.T) {
			fi := rawFormInput(t, head)
			// The request line may not parse at all; force the net/http view to agree so the
			// differential check does not mask the malformed-head check.
			fi.method, fi.target = fi.raw.Method, fi.raw.Target
			assertResult(t, checkForm(fi), false, RuleNonHTTPBytes)
		})
	}
}

// ---------------------------------------------------------------------------
// ARM B — the same bytes on a real socket, and which layer refused them
// ---------------------------------------------------------------------------

func TestFramingCorpusOnTheWire(t *testing.T) {
	for _, tc := range framingCorpus() {
		t.Run(tc.name, func(t *testing.T) {
			h := newHarness(t, harnessOpts{})
			raw, err := h.sendRaw(tc.head + tc.extra)
			if err != nil {
				t.Fatalf("send: %v", err)
			}
			status, ruleID := splitResponse(raw)
			got := whoRejected(status, ruleID)

			t.Logf("case=%s rejected_by=%q status=%q rule=%q", tc.name, got, status, ruleID)
			t.Log("net/http behaviour: " + tc.note)

			if got != tc.wantRejectedByOnTheWire {
				t.Fatalf("rejected by %q, expected %q (status %q rule %q)", got, tc.wantRejectedByOnTheWire, status, ruleID)
			}

			switch tc.wantRejectedByOnTheWire {
			case notRejected:
				if h.Capture.count() != 1 {
					t.Fatalf("the control request must reach the upstream exactly once, got %d", h.Capture.count())
				}
			default:
				if h.Capture.count() != 0 {
					t.Fatalf("a rejected request reached the pinned upstream: paths %v", h.Capture.paths())
				}
			}
			if got == byPipeline && tc.wantRule != "" && ruleID != tc.wantRule {
				t.Fatalf("rule on the wire = %q, want %q", ruleID, tc.wantRule)
			}
		})
	}
}

// TestSmuggledRequestNeverReachesUpstream is the single most important assertion in this file: the
// second request hidden after the terminating chunk must never be parsed, never be evaluated and
// never reach the target.
func TestSmuggledRequestNeverReachesUpstream(t *testing.T) {
	h := newHarness(t, harnessOpts{})
	raw := "GET /orders/1 HTTP/1.1\r\nHost: api.example.com\r\nX-F2A-Capability: " + testHandle +
		"\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n" +
		"0\r\n\r\nGET /smuggled HTTP/1.1\r\nHost: api.example.com\r\nX-F2A-Capability: " + testHandle + "\r\n\r\n"

	out, err := h.sendRaw(raw)
	if err != nil {
		t.Fatalf("send: %v", err)
	}
	if n := strings.Count(out, "HTTP/1.1 "); n != 1 {
		t.Fatalf("the connection produced %d responses; pipelining must be impossible\n%s", n, out)
	}
	for _, p := range h.Capture.paths() {
		if p == "/smuggled" {
			t.Fatal("the smuggled request reached the pinned upstream")
		}
	}
	if h.Capture.count() != 0 {
		t.Fatalf("upstream saw %d requests, want 0: %v", h.Capture.count(), h.Capture.paths())
	}
	_, ruleID := splitResponse(out)
	if ruleID != RuleAmbiguousFraming {
		t.Fatalf("rule = %q, want %s", ruleID, RuleAmbiguousFraming)
	}
}

// splitResponse returns the status line and the X-F2A-Rule-Id header, if any.
func splitResponse(raw string) (status, ruleID string) {
	lines := strings.Split(raw, "\r\n")
	if len(lines) > 0 {
		status = lines[0]
	}
	for _, ln := range lines {
		if strings.HasPrefix(strings.ToLower(ln), "x-f2a-rule-id:") {
			ruleID = strings.TrimSpace(ln[len("x-f2a-rule-id:"):])
		}
	}
	return status, ruleID
}

func whoRejected(status, ruleID string) rejector {
	if ruleID != "" && ruleID != RuleAllowed {
		return byPipeline
	}
	if strings.Contains(status, " 200 ") {
		return notRejected
	}
	if status == "" {
		// The server closed the connection without a response: net/http refused the bytes.
		return byGoServer
	}
	if strings.Contains(status, " 400 ") || strings.Contains(status, " 501 ") || strings.Contains(status, " 505 ") {
		return byGoServer
	}
	return byPipeline
}
