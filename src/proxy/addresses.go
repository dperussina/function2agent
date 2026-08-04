package main

import (
	"fmt"
	"net"
	"net/netip"
)

// Address-class denial (FR-017, constitution Principle IV bullet 1 term 4).
//
// Loopback, RFC1918 private, link-local, unique-local and the cloud-metadata address are denied
// "even when they are reached through an allowlisted host". Being allowlisted is a statement about
// a name; this is a statement about an address, and the address is what the connection goes to.
//
// This runs twice: once at configuration load, on the pinned upstream address, so a proxy pinned
// into a denied class does not start; and once on the address actually dialled, so the check holds
// on the value the kernel receives rather than on the value the operator typed.
//
// # The pinned-origin exemption (owner decision, 2026-08-03, resolving FR-017 against OD-08)
//
// FR-017 as first implemented forbade a pinned upstream on an RFC1918 address, which is the
// ordinary co-located self-hosted topology OD-08 makes the default. The resolution is NOT a flag
// and NOT a configurable range: the deny exists to stop the sandbox reaching *arbitrary* internal
// addresses, and one pinned, declared, single origin is not arbitrary.
//
// Three structural properties keep that exemption from generalising, and each has a test:
//
//  1. It is ONE ADDRESS, not a prefix, and one address in TOTAL rather than one per class.
//     `pinnedExemption` holds a single `netip.Addr` compared with `==`. There is no CIDR anywhere
//     in it, so there is no syntax in which a range could be written, and there is no second
//     field, so there is no syntax in which a second address could be written either.
//  2. It is only constructible from the pinned origin. `exemptionForPinnedOrigin` is the sole
//     constructor, it takes the address the operator declared as the upstream, and it REFUSES to
//     build an exemption for any inexemptible class. 169.254.169.254 cannot be exempted by
//     declaring it as the target.
//  3. The inexemptible classes are decided BEFORE the exemption is consulted, so no ordering
//     mistake can let one through. `exemptibleClasses` names the exemptible classes and only
//     those, and a test asserts both its exact membership and that link-local, cloud-metadata,
//     unique-local and unspecified are absent from it.
//
// # Loopback (owner decision, 2026-08-03, extending the above)
//
// Loopback was initially left OUT of the exemption, because the first decision named the RFC1918
// deny and widening it would have been this component choosing a scope the decision did not
// grant. That left an incoherence: a same-host deployment at 127.0.0.1 was denied while the
// identical deployment one hop away on an RFC1918 address was permitted. The owner extended the
// exemption to a declared loopback origin on exactly the same terms — single address, equality
// comparison, sole constructor, decided after the inexemptible classes.
//
// The exemptible set is now two classes and STILL one address: which class the declared origin
// falls in decides whether an exemption may be built at all, never how many may exist. A
// deployment declares one upstream address, so it obtains one exemption or none.
//
// Link-local, cloud-metadata, unique-local and unspecified remain inexemptible by every path.

// Named address classes, used as the denial detail so the operator sees which class matched.
const (
	classLoopback    = "loopback"
	classPrivate     = "rfc1918_private"
	classLinkLocal   = "link_local"
	classUniqueLocal = "unique_local"
	classMetadata    = "cloud_metadata"
	classUnspecified = "unspecified"
)

// cloudMetadataAddr is the link-local address every major cloud serves instance credentials on.
// It is inside 169.254.0.0/16 and would be caught by the link-local rule anyway; it is named
// separately because FR-017 names it separately and because the denial detail should say so.
var cloudMetadataAddr = netip.MustParseAddr("169.254.169.254")

var deniedPrefixes = []struct {
	prefix netip.Prefix
	class  string
}{
	{netip.MustParsePrefix("127.0.0.0/8"), classLoopback},
	{netip.MustParsePrefix("::1/128"), classLoopback},
	{netip.MustParsePrefix("10.0.0.0/8"), classPrivate},
	{netip.MustParsePrefix("172.16.0.0/12"), classPrivate},
	{netip.MustParsePrefix("192.168.0.0/16"), classPrivate},
	{netip.MustParsePrefix("169.254.0.0/16"), classLinkLocal},
	{netip.MustParsePrefix("fe80::/10"), classLinkLocal},
	{netip.MustParsePrefix("fc00::/7"), classUniqueLocal},
	{netip.MustParsePrefix("0.0.0.0/32"), classUnspecified},
	{netip.MustParsePrefix("::/128"), classUnspecified},
}

// exemptibleClasses names every denied class from which the declared target origin may be
// exempted. It has exactly two members, on purpose: the two ways the OD-08 co-located topology
// reaches its own application, depending on whether the deployment shares a host with it.
//
// Membership here decides WHETHER an exemption may be built, never HOW MANY may exist — see
// pinnedExemption, which holds one address whatever this set contains.
//
// TestExemptibleClassesIsExactlyPrivateAndLoopback asserts the exact membership and the absence
// of link_local, cloud_metadata, unique_local and unspecified, so adding a class here is a test
// failure and not a quiet policy change.
var exemptibleClasses = map[string]bool{
	classPrivate:  true,
	classLoopback: true,
}

// pinnedExemption is the declared target origin's address, or the zero value for no exemption.
//
// A struct wrapping one `netip.Addr` rather than a bare address, so that "no exemption" is a
// distinct, obviously-empty value at every call site, and so the type cannot be widened into a
// list or a prefix without changing every one of them.
//
// ONE FIELD, and that is the containment that survives the exemptible set growing. Two exemptible
// classes could have meant one exemption per class; it does not, because there is nowhere to put
// a second address. TestTheExemptionHoldsExactlyOneAddress asserts the field count against the
// type, so adding a slot is a test failure rather than a quiet widening.
type pinnedExemption struct {
	addr netip.Addr
}

// noExemption is the value every path that has no declared origin in hand must pass. It exists so
// that "I have no exemption" is written explicitly rather than being the accidental result of a
// zero value nobody thought about.
var noExemption = pinnedExemption{}

// exempts reports whether addr is the single declared origin.
func (e pinnedExemption) exempts(addr netip.Addr) bool {
	return e.addr.IsValid() && e.addr == addr
}

// ExemptionError is returned when an exemption is requested for a class that has no exemption
// path. It is a startup error: the operator declared a target the deny cannot be lifted for.
type ExemptionError struct {
	Addr  string
	Class string
}

func (e *ExemptionError) Error() string {
	return fmt.Sprintf(
		"address %s is in class %s, which has no exemption path under any configuration (FR-017)",
		e.Addr, e.Class)
}

// exemptionForPinnedOrigin builds the one exemption this component will honour, from the address
// the operator declared as the upstream. It is the ONLY constructor of a non-empty exemption.
//
// An address in an inexemptible denied class is an error rather than an exemption, which is what
// makes "declare the metadata service as your target" a startup failure instead of a bypass.
//
// It takes ONE address and returns ONE exemption, so it cannot be the route by which a deployment
// accumulates an exemption per exemptible class. Its single production caller, validatePinnedAddr,
// is reached once per process from the single declared upstream.
func exemptionForPinnedOrigin(addr netip.Addr) (pinnedExemption, error) {
	if !addr.IsValid() {
		return noExemption, &ExemptionError{Addr: addr.String(), Class: classUnspecified}
	}
	a := addr.Unmap()
	class, denied := classify(a)
	if !denied {
		// Not in a denied class, so no exemption is needed. Returning the empty exemption
		// rather than one naming this address keeps the exemption's blast radius at zero
		// for the ordinary public-origin deployment.
		return noExemption, nil
	}
	if !exemptibleClasses[class] {
		return noExemption, &ExemptionError{Addr: a.String(), Class: class}
	}
	return pinnedExemption{addr: a}, nil
}

// AddressClassError is the typed error the dialer returns when the address it is about to dial is
// in a denied class. The pipeline maps it to EG-ADDR-001 rather than to a generic transport
// failure, so the denial is attributable to FR-017.
type AddressClassError struct {
	Addr  string
	Class string
}

func (e *AddressClassError) Error() string {
	return fmt.Sprintf("address %s is in denied class %s (FR-017)", e.Addr, e.Class)
}

// classify names the denied class addr belongs to, and true, or "" and false. It knows nothing
// about exemptions: it is the statement of what FR-017 denies, kept separate from the statement of
// what one declared origin may be excused from, so the second cannot quietly edit the first.
//
// IPv4-mapped IPv6 addresses are unmapped by the caller: ::ffff:127.0.0.1 is loopback.
func classify(a netip.Addr) (string, bool) {
	if a == cloudMetadataAddr {
		return classMetadata, true
	}
	for _, d := range deniedPrefixes {
		if d.prefix.Contains(a) {
			return d.class, true
		}
	}
	return "", false
}

// deniedAddressClass returns the name of the denied class addr belongs to, and true, or "" and
// false, honouring at most the one declared-origin exemption.
//
// The order below is the safety property. An inexemptible class is decided and returned before the
// exemption is looked at, so a bug in the exemption cannot reach link-local or the metadata
// service — there is no code path from here to `exempt` for those classes at all.
func deniedAddressClass(addr netip.Addr, exempt pinnedExemption) (string, bool) {
	if !addr.IsValid() {
		// An address that will not parse cannot be shown to be outside the denied classes.
		return classUnspecified, true
	}
	a := addr.Unmap()
	class, denied := classify(a)
	if !denied {
		return "", false
	}
	if !exemptibleClasses[class] {
		return class, true
	}
	if exempt.exempts(a) {
		return "", false
	}
	return class, true
}

// checkDialAddress validates a "host:port" pair that is about to be dialled. The host must be a
// literal IP: a name here would mean a resolution, and FR-016 forbids re-resolving per request.
//
// `exempt` is passed explicitly at every call site rather than read from a package variable, so
// that a path with no declared origin in hand cannot inherit one from somewhere else.
func checkDialAddress(hostPort string, exempt pinnedExemption) error {
	host, port, err := net.SplitHostPort(hostPort)
	if err != nil {
		return fmt.Errorf("address %q is not a valid host:port: %w", hostPort, err)
	}
	if port == "" {
		return fmt.Errorf("address %q has no port; FR-016 pins at host-and-port granularity", hostPort)
	}
	addr, err := netip.ParseAddr(host)
	if err != nil {
		// Not a literal IP. Dialling it would require a resolver, which this component does
		// not have and FR-016 does not permit per request.
		return fmt.Errorf("address %q does not contain a literal IP; names are never resolved (FR-016)", hostPort)
	}
	if class, denied := deniedAddressClass(addr, exempt); denied {
		return &AddressClassError{Addr: hostPort, Class: class}
	}
	return nil
}
