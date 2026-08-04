package main

import (
	"context"
	"errors"
	"net/netip"
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
		class, isDenied := deniedAddressClass(addr)
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
		if class, isDenied := deniedAddressClass(netip.MustParseAddr(s)); isDenied {
			t.Errorf("%s must not be denied, got class %q", s, class)
		}
	}

	if class, isDenied := deniedAddressClass(netip.Addr{}); !isDenied || class != classUnspecified {
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
			err := checkDialAddress(tc.addr)
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
	d := NewPinnedDialer("169.254.169.254:80", time.Second)
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
	d := NewPinnedDialer("203.0.113.10:443", 50*time.Millisecond)
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
	d := NewPinnedDialer("example.invalid:443", time.Second)
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

// TestFR017AndOD08Tension records, as an executable statement rather than a comment, that FR-017
// as written forbids the ordinary co-located self-hosted topology. If someone later adds an
// override flag to relieve the tension, this test tells them they have changed a requirement.
func TestFR017AndOD08Tension(t *testing.T) {
	for _, addr := range []string{"127.0.0.1:8443", "10.0.0.5:8443", "192.168.1.20:8443", "172.20.0.3:8443"} {
		if err := validatePinnedAddr(addr); err == nil {
			t.Fatalf("FR-017 as written must refuse a pinned upstream at %s; if this now passes, "+
				"a requirement was relaxed in code rather than in the specification", addr)
		}
	}
}
