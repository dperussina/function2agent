package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"testing"
)

// The fail-closed proofs.
//
// Each test here removes one of the sequencer's structural guarantees and asserts the request is
// denied anyway. Every one of them fails if the corresponding mechanism in pipeline.go is removed.

// ---------------------------------------------------------------------------
// Stage stubs
// ---------------------------------------------------------------------------

type fnStage struct {
	stageName
	fn      func(*requestContext) (stageResult, error)
	entered *int
}

func (s fnStage) Evaluate(_ context.Context, rc *requestContext) (stageResult, error) {
	if s.entered != nil {
		*s.entered++
	}
	return s.fn(rc)
}

func allowStage(name string, entered *int) fnStage {
	return fnStage{stageName: stageName(name), entered: entered,
		fn: func(rc *requestContext) (stageResult, error) { return allowResult(), nil }}
}

// zeroValueStage returns the zero value of stageResult and nothing else. It is the proof that the
// zero value denies.
func zeroValueStage(name string) fnStage {
	return fnStage{stageName: stageName(name),
		fn: func(*requestContext) (stageResult, error) {
			var res stageResult // untouched
			return res, nil
		}}
}

func errorStage(name string, err error) fnStage {
	return fnStage{stageName: stageName(name),
		fn: func(*requestContext) (stageResult, error) { return stageResult{}, err }}
}

func panicStage(name string) fnStage {
	return fnStage{stageName: stageName(name),
		fn: func(*requestContext) (stageResult, error) { panic("stage exploded") }}
}

// countingFinal records whether stage 7 ran.
type countingFinal struct {
	stageName
	runs int
	err  error
}

func (f *countingFinal) Deliver(_ context.Context, w http.ResponseWriter, _ *requestContext) error {
	f.runs++
	if f.err != nil {
		return f.err
	}
	w.WriteHeader(http.StatusOK)
	return nil
}

func newTestPipeline(stages []Stage, final FinalStage) (*Pipeline, *recordingSink) {
	sink := &recordingSink{}
	p, err := ParsePolicy([]byte(testPolicyJSON))
	if err != nil {
		panic(err)
	}
	return NewPipeline(stages, final, sink, p, "sha256:testfpr"), sink
}

func decideOnce(p *Pipeline) (stageResult, *requestContext) {
	rc := &requestContext{Method: "GET", Path: "/orders/1", RawTarget: "/orders/1", Tier: tierUnresolved}
	return p.Decide(context.Background(), rc), rc
}

// ---------------------------------------------------------------------------
// The zero value denies
// ---------------------------------------------------------------------------

func TestZeroValueStageResultIsDeny(t *testing.T) {
	var zero stageResult
	if zero.allowed {
		t.Fatal("the zero value of stageResult must not be an allow")
	}
	if zero.ruleID != "" {
		t.Fatalf("the zero value must not name a rule; got %q", zero.ruleID)
	}
}

// TestStageReturningZeroValueDenies injects a stage that returns the zero value — a stage that
// simply forgot to decide — and asserts the request is denied and stage 7 never runs.
func TestStageReturningZeroValueDenies(t *testing.T) {
	final := &countingFinal{stageName: "final"}
	p, sink := newTestPipeline([]Stage{
		allowStage("one", nil),
		zeroValueStage("two"),
		allowStage("three", nil),
	}, final)

	res, _ := decideOnce(p)
	assertResult(t, res, false, RuleNoStageAllowed)
	if final.runs != 0 {
		t.Fatal("stage 7 ran after a stage returned the zero value")
	}
	_ = sink
}

// ---------------------------------------------------------------------------
// An erroring stage denies with EG-PIPE-001
// ---------------------------------------------------------------------------

func TestStageErrorDeniesWithPipe001(t *testing.T) {
	final := &countingFinal{stageName: "final"}
	p, _ := newTestPipeline([]Stage{
		allowStage("one", nil),
		errorStage("two", errors.New("database unreachable")),
	}, final)

	res, _ := decideOnce(p)
	assertResult(t, res, false, RuleStageError)
	if final.runs != 0 {
		t.Fatal("stage 7 ran after a stage errored")
	}
	if got := ruleReason(res.ruleID); got != "stage_error_fail_closed" {
		t.Fatalf("reason = %q", got)
	}
}

// ---------------------------------------------------------------------------
// A panicking stage denies with EG-PIPE-002
// ---------------------------------------------------------------------------

func TestStagePanicDeniesWithPipe002(t *testing.T) {
	final := &countingFinal{stageName: "final"}
	p, _ := newTestPipeline([]Stage{
		allowStage("one", nil),
		panicStage("two"),
		allowStage("three", nil),
	}, final)

	res, _ := decideOnce(p)
	assertResult(t, res, false, RuleStagePanic)
	if final.runs != 0 {
		t.Fatal("stage 7 ran after a stage panicked")
	}
}

// ---------------------------------------------------------------------------
// Reaching the end without every stage allowing denies with EG-PIPE-003
// ---------------------------------------------------------------------------

func TestEmptyPipelineDeniesWithPipe003(t *testing.T) {
	final := &countingFinal{stageName: "final"}
	p, _ := newTestPipeline(nil, final)
	res, _ := decideOnce(p)
	assertResult(t, res, false, RuleNoStageAllowed)
	if final.runs != 0 {
		t.Fatal("stage 7 ran with no stages registered")
	}
}

// TestDenyWithNoRuleIdBecomesPipe003 covers a stage that denies but names no rule, and a stage
// that names a rule the registry does not contain. Neither may produce a denial with no rule
// identifier.
func TestDenyWithNoRuleIdBecomesPipe003(t *testing.T) {
	cases := []struct {
		name string
		res  stageResult
	}{
		{"empty_rule_id", stageResult{allowed: false, ruleID: "", detail: "forgot"}},
		{"unregistered_rule_id", stageResult{allowed: false, ruleID: "EG-MADE-UP-999"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			final := &countingFinal{stageName: "final"}
			res := tc.res
			p, _ := newTestPipeline([]Stage{
				fnStage{stageName: "bad", fn: func(*requestContext) (stageResult, error) { return res, nil }},
			}, final)
			got, _ := decideOnce(p)
			assertResult(t, got, false, RuleNoStageAllowed)
			if final.runs != 0 {
				t.Fatal("stage 7 ran")
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Every stage in the registered order must allow before stage 7 runs
// ---------------------------------------------------------------------------

func TestEveryStageMustAllowBeforeStageSeven(t *testing.T) {
	const n = 6
	for denyAt := 0; denyAt < n; denyAt++ {
		t.Run(fmt.Sprintf("deny_at_%d", denyAt), func(t *testing.T) {
			entered := make([]int, n)
			stages := make([]Stage, 0, n)
			for i := 0; i < n; i++ {
				i := i
				stages = append(stages, fnStage{
					stageName: stageName(fmt.Sprintf("s%d", i)),
					entered:   &entered[i],
					fn: func(*requestContext) (stageResult, error) {
						if i == denyAt {
							return denyResult(RuleMethodNotAllowed, "injected"), nil
						}
						return allowResult(), nil
					},
				})
			}
			final := &countingFinal{stageName: "final"}
			p, _ := newTestPipeline(stages, final)

			res, _ := decideOnce(p)
			assertResult(t, res, false, RuleMethodNotAllowed)
			if final.runs != 0 {
				t.Fatalf("stage 7 ran although stage %d denied", denyAt)
			}
			for i := 0; i <= denyAt; i++ {
				if entered[i] != 1 {
					t.Errorf("stage %d entered %d times, want 1", i, entered[i])
				}
			}
			for i := denyAt + 1; i < n; i++ {
				if entered[i] != 0 {
					t.Errorf("stage %d ran after stage %d denied", i, denyAt)
				}
			}
		})
	}

	t.Run("all_allow_reaches_stage_seven", func(t *testing.T) {
		entered := make([]int, n)
		stages := make([]Stage, 0, n)
		for i := 0; i < n; i++ {
			stages = append(stages, allowStage(fmt.Sprintf("s%d", i), &entered[i]))
		}
		final := &countingFinal{stageName: "final"}
		p, sink := newTestPipeline(stages, final)

		res, rc := decideOnce(p)
		assertResult(t, res, true, RuleAllowed)
		// Decide does not itself run stage 7; ServeHTTP does. Prove the wiring end to end.
		rec := httptestRecorder()
		_ = rc
		p.ServeHTTP(rec, mustRequest(t, "GET", "/orders/1"))
		if final.runs != 1 {
			t.Fatalf("stage 7 ran %d times, want 1", final.runs)
		}
		recs := sink.all()
		if len(recs) == 0 {
			t.Fatal("no decision recorded for an allowed request")
		}
		if recs[len(recs)-1].RuleID() != RuleAllowed {
			t.Fatalf("allow record rule = %q", recs[len(recs)-1].RuleID())
		}
	})
}

// ---------------------------------------------------------------------------
// An unrecordable decision is not a permitted decision
// ---------------------------------------------------------------------------

func TestUnwritableDecisionLogFailsClosed(t *testing.T) {
	final := &countingFinal{stageName: "final"}
	sink := &recordingSink{failWith: errors.New("disk full")}
	p, err := ParsePolicy([]byte(testPolicyJSON))
	if err != nil {
		t.Fatal(err)
	}
	pipe := NewPipeline([]Stage{allowStage("one", nil)}, final, sink, p, "")

	rec := httptestRecorder()
	pipe.ServeHTTP(rec, mustRequest(t, "GET", "/orders/1"))
	if final.runs != 0 {
		t.Fatal("stage 7 ran although the decision could not be recorded")
	}
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", rec.Code)
	}
	if got := rec.Header().Get("X-F2A-Rule-Id"); got != RuleStageError {
		t.Fatalf("rule = %q, want %s", got, RuleStageError)
	}
}

// ---------------------------------------------------------------------------
// Stage 7's own tier guard
// ---------------------------------------------------------------------------

// TestUnresolvedNeverReachesFinal proves the claim made in effect.go: stage 5 allows an unresolved
// call so that stage 6 can name it operation_unresolvable, and that is safe because the pipeline
// is a conjunction. Removing stage 6 from the registered order is also covered — stage 7's own
// guard refuses a non-read_only tier.
func TestUnresolvedNeverReachesFinal(t *testing.T) {
	policy := mustTestPolicy(t)

	t.Run("stage6_denies_it", func(t *testing.T) {
		final := &countingFinal{stageName: "final"}
		p, _ := newTestPipeline([]Stage{NewEffectStage(policy), NewUnresolvableStage()}, final)
		rc := &requestContext{Method: "GET", Path: "/not-served", Tier: tierUnresolved}
		res := p.Decide(context.Background(), rc)
		assertResult(t, res, false, RuleOperationUnresolvable)
		if final.runs != 0 {
			t.Fatal("stage 7 ran on an unresolvable operation")
		}
	})

	t.Run("stage7_guard_refuses_without_stage6", func(t *testing.T) {
		reo := NewReoriginator(ReoriginatorConfig{
			Origin:           PinnedOrigin{Scheme: "https", Host: "example.com", Port: "443"},
			CredentialHeader: testCredentialHdr,
			Credential:       NewSecret(testCredentialValue),
			Dialer:           &stubDialer{target: "127.0.0.1:1"},
		})
		rc := &requestContext{Method: "GET", Path: "/not-served", Tier: tierUnresolved}
		err := reo.Deliver(context.Background(), httptestRecorder(), rc)
		if err == nil {
			t.Fatal("stage 7 must refuse a non-read_only tier")
		}
		var tg *tierGuardError
		if !errors.As(err, &tg) {
			t.Fatalf("want tierGuardError, got %v", err)
		}
		assertResult(t, classifyDeliveryError(err), false, RuleTierNotReadOnly)
	})
}
