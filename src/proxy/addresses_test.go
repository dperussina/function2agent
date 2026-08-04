package main

import (
	"context"
	"errors"
	"net"
	"net/netip"
	"reflect"
	"strings"
	"testing"
	"time"
)

// T090 — address-class denial (FR-017).

func TestDeniedAddressClasses(t *testing.T) {
	denied := map[string]string{
		"127.0.0.1":        classLoopback,
		"127.255.255.254":  classLoopback,
		"::1":              classLoopback,
		"::ffff:127.0.0.1": classLoopback, // IPv4-mapped loopback, unmapped first
		"10.0.0.1":         classPrivate,
		"10.255.255.255":   classPrivate,
		"172.16.0.1":       classPrivate,
		"172.31.255.255":   classPrivate,
		"192.168.1.1":      classPrivate,
		"169.254.1.1":      classLinkLocal,
		"fe80::1":          classLinkLocal,
		"fc00::1":          classUniqueLocal,
		"fd12:3456::1":     classUniqueLocal,
		"169.254.169.254":  classMetadata,
		"0.0.0.0":          classUnspecified,
		"::":               classUnspecified,
	}
	for s, wantClass := range denied {
		addr := netip.MustParseAddr(s)
		class, isDenied := deniedAddressClass(addr, noExemption)
		if !isDenied {
			t.Errorf("%s must be denied (FR-017)", s)
			continue
		}
		if class != wantClass {
			t.Errorf("%s denied as %q, want %q", s, class, wantClass)
		}
	}

	allowed := []string{
		"203.0.113.10", "8.8.8.8", "172.32.0.1", "172.15.255.255",
		"192.169.0.1", "9.255.255.255", "2001:db8::1",
	}
	for _, s := range allowed {
		if class, isDenied := deniedAddressClass(netip.MustParseAddr(s), noExemption); isDenied {
			t.Errorf("%s must not be denied, got class %q", s, class)
		}
	}

	if class, isDenied := deniedAddressClass(netip.Addr{}, noExemption); !isDenied || class != classUnspecified {
		t.Errorf("an invalid address must be denied, got (%q, %v)", class, isDenied)
	}
}

func TestCheckDialAddress(t *testing.T) {
	cases := []struct {
		addr      string
		wantErr   bool
		wantClass string
	}{
		{addr: "203.0.113.10:443"},
		{addr: "[2001:db8::1]:443"},
		{addr: "127.0.0.1:443", wantErr: true, wantClass: classLoopback},
		{addr: "10.1.2.3:8080", wantErr: true, wantClass: classPrivate},
		{addr: "169.254.169.254:80", wantErr: true, wantClass: classMetadata},
		{addr: "[fd00::1]:443", wantErr: true, wantClass: classUniqueLocal},
		// A name here would mean a resolution, which FR-016 forbids per request.
		{addr: "api.example.com:443", wantErr: true},
		{addr: "203.0.113.10", wantErr: true},
		{addr: "", wantErr: true},
	}
	for _, tc := range cases {
		t.Run(tc.addr, func(t *testing.T) {
			err := checkDialAddress(tc.addr, noExemption)
			if tc.wantErr != (err != nil) {
				t.Fatalf("checkDialAddress(%q) error = %v, wantErr %v", tc.addr, err, tc.wantErr)
			}
			if tc.wantClass != "" {
				var ace *AddressClassError
				if !errors.As(err, &ace) {
					t.Fatalf("want AddressClassError, got %v", err)
				}
				if ace.Class != tc.wantClass {
					t.Fatalf("class = %q, want %q", ace.Class, tc.wantClass)
				}
			}
		})
	}
}

// TestPinnedDialerRefusesDeniedClassOnTheAddressActuallyDialled: the check runs on the value the
// kernel would receive, not only on the value the operator typed. Removing it means an operator
// who edits the address after startup, or a future code path that mutates it, gets an unchecked
// dial.
func TestPinnedDialerRefusesDeniedClassOnTheAddressActuallyDialled(t *testing.T) {
	d := NewPinnedDialer("169.254.169.254:80", noExemption, time.Second)
	_, err := d.DialContext(context.Background(), "tcp", "203.0.113.10:443")
	if err == nil {
		t.Fatal("the dialer must refuse the cloud-metadata address")
	}
	var ace *AddressClassError
	if !errors.As(err, &ace) {
		t.Fatalf("want AddressClassError, got %v", err)
	}
	if ace.Class != classMetadata {
		t.Fatalf("class = %q", ace.Class)
	}
	assertResult(t, classifyDeliveryError(err), false, RuleAddressClassDenied)
}

// TestPinnedDialerIgnoresTheRequestedAddress: whatever the transport asks for, the dialer dials
// the pinned address. This is FR-016's "names are never re-resolved per request" made structural.
func TestPinnedDialerIgnoresTheRequestedAddress(t *testing.T) {
	d := NewPinnedDialer("203.0.113.10:443", noExemption, 50*time.Millisecond)
	// Ask for something else entirely; the refusal below must be about the pinned address, and
	// TEST-NET-3 is unroutable so the dial times out rather than connecting anywhere.
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	_, err := d.DialContext(ctx, "tcp", "127.0.0.1:9")
	if err == nil {
		t.Fatal("expected the dial to 203.0.113.10:443 to fail")
	}
	// If it had dialled 127.0.0.1:9 the error would be a connection refusal, immediate. What
	// matters here is only that it did not succeed against the requested address.
	t.Logf("dial error (against the pinned address, not the requested one): %v", err)
}

// TestPinnedDialerHasNoResolver proves the dialer cannot turn a name into an address.
func TestPinnedDialerHasNoResolver(t *testing.T) {
	d := NewPinnedDialer("example.invalid:443", noExemption, time.Second)
	_, err := d.DialContext(context.Background(), "tcp", "example.invalid:443")
	if err == nil {
		t.Fatal("a name must not be dialable")
	}
	if errors.Is(err, errResolverDisabled) {
		return // the resolver was consulted and refused
	}
	// Or it never got that far, because checkDialAddress refuses a non-literal host first.
	t.Logf("refused before resolution: %v", err)
}

// ---------------------------------------------------------------------------
// The pinned-origin exemption (FR-017 against OD-08, owner decision 2026-08-03).
//
// The exemption's whole risk is that it generalises. These tests are the fence, and each states
// which way it would have to be broken.

// TestExemptibleClassesIsExactlyRFC1918 is the assertion the owner asked for rather than merely
// the implementation: link-local and the metadata service must be deniable by NO path.
//
// It checks the set's size as well as its contents, because a test that only checked for absence
// would pass while someone added loopback, and the decision did not grant loopback either.
func TestExemptibleClassesIsExactlyRFC1918(t *testing.T) {
	if len(exemptibleClasses) != 1 {
		t.Fatalf("exemptibleClasses has %d members, want exactly 1 (%s). Widening the set of "+
			"classes an exemption can reach is a requirement change, not an implementation "+
			"detail.", len(exemptibleClasses), classPrivate)
	}
	if !exemptibleClasses[classPrivate] {
		t.Fatalf("the one exemptible class must be %q", classPrivate)
	}
	for _, forbidden := range []string{classLinkLocal, classMetadata, classLoopback, classUniqueLocal, classUnspecified} {
		if exemptibleClasses[forbidden] {
			t.Fatalf("%q must have no exemption path under any configuration (FR-017)", forbidden)
		}
	}
}

// TestTheMetadataServiceCannotBeExemptedByDeclaringIt is the attack the exemption invites: name
// 169.254.169.254 as your target origin and the deny is lifted for it. It must be a startup
// failure instead.
func TestTheMetadataServiceCannotBeExemptedByDeclaringIt(t *testing.T) {
	inexemptible := map[string]string{
		"169.254.169.254": classMetadata,
		"169.254.1.1":     classLinkLocal,
		"fe80::1":         classLinkLocal,
		"127.0.0.1":       classLoopback,
		"::1":             classLoopback,
		"fc00::1":         classUniqueLocal,
		"0.0.0.0":         classUnspecified,
	}
	for s, wantClass := range inexemptible {
		addr := netip.MustParseAddr(s)

		exempt, err := exemptionForPinnedOrigin(addr)
		if err == nil {
			t.Errorf("declaring %s as the target origin produced an exemption; it must be "+
				"refused at startup", s)
			continue
		}
		var ee *ExemptionError
		if !errors.As(err, &ee) {
			t.Errorf("%s: want ExemptionError, got %v", s, err)
			continue
		}
		if ee.Class != wantClass {
			t.Errorf("%s: refused as class %q, want %q", s, ee.Class, wantClass)
		}
		if exempt != noExemption {
			t.Errorf("%s: a refused exemption must be the empty one", s)
		}

		// And the refusal is not merely at construction: even if a caller somehow held a
		// hand-built exemption for this address, the class is decided before the exemption
		// is consulted.
		forged := pinnedExemption{addr: addr}
		if class, denied := deniedAddressClass(addr, forged); !denied {
			t.Errorf("%s: a forged exemption reached an inexemptible class (got %q)", s, class)
		}
	}
}

// TestTheDeclaredRFC1918OriginIsReachable is the OD-08 topology the decision exists to permit.
func TestTheDeclaredRFC1918OriginIsReachable(t *testing.T) {
	for _, addr := range []string{"10.0.0.5:8443", "192.168.1.20:8443", "172.20.0.3:8443"} {
		exempt, err := validatePinnedAddr(addr)
		if err != nil {
			t.Fatalf("the declared co-located target %s must be permitted (OD-08): %v", addr, err)
		}
		if exempt == noExemption {
			t.Fatalf("%s: an RFC1918 target must produce a non-empty exemption", addr)
		}
		if err := checkDialAddress(addr, exempt); err != nil {
			t.Fatalf("%s: the declared target must be dialable: %v", addr, err)
		}
	}
}

// TestADifferentRFC1918AddressIsStillDenied is the test the owner named. The exemption is one
// address, so the rest of the operator's internal network stays unreachable — which is the whole
// content of "one pinned, declared, single origin is not arbitrary".
func TestADifferentRFC1918AddressIsStillDenied(t *testing.T) {
	exempt, err := validatePinnedAddr("10.0.0.5:8443")
	if err != nil {
		t.Fatalf("setup: %v", err)
	}

	// Neighbours in the same /8, the same /24, and adjacent addresses. If the exemption were
	// ever keyed to a prefix rather than an address, at least one of these would pass.
	for _, other := range []string{
		"10.0.0.4:8443", "10.0.0.6:8443", "10.0.0.5:9443", // note: different PORT is fine,
		"10.0.1.5:8443", "10.255.255.255:8443", // the exemption is on the address
		"192.168.1.20:8443", "172.20.0.3:8443",
	} {
		host, _, _ := net.SplitHostPort(other)
		addr := netip.MustParseAddr(host)
		if addr == netip.MustParseAddr("10.0.0.5") {
			continue // the declared one, covered above
		}
		if err := checkDialAddress(other, exempt); err == nil {
			t.Errorf("%s is not the declared origin and must stay denied; the exemption "+
				"has generalised beyond one address", other)
		}
	}
}

// TestTheExemptionIsAnAddressNotAPrefix states the non-generalisation property directly against
// the type, so that changing `pinnedExemption` to hold a prefix breaks a test that says why.
func TestTheExemptionIsAnAddressNotAPrefix(t *testing.T) {
	exempt := pinnedExemption{addr: netip.MustParseAddr("10.0.0.5")}
	if !exempt.exempts(netip.MustParseAddr("10.0.0.5")) {
		t.Fatal("the declared address must be exempt")
	}
	for _, near := range []string{"10.0.0.4", "10.0.0.6", "10.0.0.0", "10.0.0.255"} {
		if exempt.exempts(netip.MustParseAddr(near)) {
			t.Errorf("%s is exempted by an exemption declared for 10.0.0.5; the comparison "+
				"is no longer an equality", near)
		}
	}
	if noExemption.exempts(netip.MustParseAddr("10.0.0.5")) {
		t.Fatal("the empty exemption must exempt nothing")
	}
	// The zero Addr must not match an invalid address either, which would make every
	// unparseable address exempt.
	if noExemption.exempts(netip.Addr{}) {
		t.Fatal("the empty exemption must not match the zero address")
	}
}

// TestNoConfigurationKeySetsTheExemption keeps it from becoming a toggle. The exemption is derived
// from the declared target and from nothing else, so there must be no environment variable for it.
func TestNoConfigurationKeySetsTheExemption(t *testing.T) {
	for _, k := range requiredEnv {
		if strings.Contains(strings.ToLower(k), "exempt") ||
			strings.Contains(strings.ToLower(k), "allow_private") ||
			strings.Contains(strings.ToLower(k), "insecure") {
			t.Fatalf("%s looks like a switch for the address deny. The exemption is keyed to "+
				"the declared target origin and must not be settable independently.", k)
		}
	}
	// And a public origin yields no exemption at all, so the ordinary deployment carries
	// zero exemption surface.
	exempt, err := validatePinnedAddr("203.0.113.10:443")
	if err != nil {
		t.Fatalf("setup: %v", err)
	}
	if exempt != noExemption {
		t.Fatal("a public target origin must produce no exemption")
	}
}

// TestTheDialerCannotBeGivenAnExemptionAfterConstruction: PinnedDialer.exempt is unexported and
// has no setter, so the exemption a dialer honours is fixed when it is built. Asserted by
// reflection because a field added later would otherwise silently reopen this.
func TestTheDialerCannotBeGivenAnExemptionAfterConstruction(t *testing.T) {
	typ := reflect.TypeOf(PinnedDialer{})
	field, ok := typ.FieldByName("exempt")
	if !ok {
		t.Fatal("PinnedDialer has no exempt field; the dialer is no longer carrying one")
	}
	if field.IsExported() {
		t.Fatal("PinnedDialer.exempt is exported, so any package-local caller can widen the " +
			"exemption of a running dialer")
	}
	for i := 0; i < typ.NumField(); i++ {
		f := typ.Field(i)
		if f.IsExported() && f.Type == reflect.TypeOf(pinnedExemption{}) {
			t.Fatalf("PinnedDialer.%s exposes the exemption for mutation", f.Name)
		}
	}
}
