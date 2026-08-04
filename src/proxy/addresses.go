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
// IMPLEMENTED AS WRITTEN, AND IT IS IN TENSION WITH OD-08. FR-017 as written forbids a pinned
// upstream on an RFC1918 address, which is the ordinary co-located self-hosted topology OD-08
// makes the default. There is deliberately no override flag here: the strict reading is
// implemented and the tension is reported rather than resolved in code.

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

// deniedAddressClass returns the name of the denied class addr belongs to, and true, or "" and
// false. IPv4-mapped IPv6 addresses are unmapped first: ::ffff:127.0.0.1 is loopback.
func deniedAddressClass(addr netip.Addr) (string, bool) {
	if !addr.IsValid() {
		// An address that will not parse cannot be shown to be outside the denied classes.
		return classUnspecified, true
	}
	a := addr.Unmap()
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

// checkDialAddress validates a "host:port" pair that is about to be dialled. The host must be a
// literal IP: a name here would mean a resolution, and FR-016 forbids re-resolving per request.
func checkDialAddress(hostPort string) error {
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
	if class, denied := deniedAddressClass(addr); denied {
		return &AddressClassError{Addr: hostPort, Class: class}
	}
	return nil
}
