# T159 — the enforcement-point image. Linux only, no degraded mode (OD-17).
#
# Process: the Go binary built from `src/proxy`. `main` ends in
# `ServeEnforcement` on `F2A_PROXY_LISTEN` (a Go env, not a Python key).
#
# Go is installed in the builder with a required checksum and no default —
# the same SBX-IMG-005 correction T096 recorded on `dev.Dockerfile`. An
# unpinned `GO_SHA256` here would be that regression. The shipped stage copies
# the static binary and does not contain a Go toolchain, a fetch, or a
# package index (`GOPROXY` is builder-only).
#
# `image_policy.py` does not walk this file: SBX-IMG-001 is a pip-lock rule
# and this image's lock is `src/proxy/go.sum`. A dedicated test asserts the
# shipped stage still has no fetch and no GO_SHA256 default.
#
# Holds the target credential at run time via environment injection, never
# baked into a layer. The sandbox image holds neither plane.
#
# Build:
#   docker build -f deploy/images/enforcement.Dockerfile \
#     --build-arg GO_SHA256=<sha256 of go${GO_VERSION}.linux-${TARGETARCH}.tar.gz> \
#     -t f2a-enforcement .

FROM debian:bookworm-slim AS builder

ARG GO_VERSION=1.24.3
ARG TARGETARCH
ARG GO_SHA256
RUN set -eux; \
    if [ -z "${GO_SHA256:-}" ]; then \
      echo "GO_SHA256 is required: pass the checksum published for"; \
      echo "go${GO_VERSION}.linux-${TARGETARCH}.tar.gz at https://go.dev/dl/"; \
      echo "  docker build --build-arg GO_SHA256=<sha256> ..."; \
      exit 1; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    url="https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz"; \
    curl -fsSL "$url" -o /tmp/go.tgz; \
    echo "${GO_SHA256}  /tmp/go.tgz" | sha256sum -c -; \
    tar -C /usr/local -xzf /tmp/go.tgz; \
    rm /tmp/go.tgz; \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/go/bin:${PATH}" \
    CGO_ENABLED=0 \
    GOFLAGS="-mod=mod"

WORKDIR /src/proxy
COPY src/proxy/go.mod src/proxy/go.sum ./
RUN go mod download
COPY src/proxy ./
RUN go build -o /out/f2a-enforcement .

FROM debian:bookworm-slim AS enforcement

COPY --from=builder /out/f2a-enforcement /usr/local/bin/f2a-enforcement

# The shipped stage must not mention a fetcher by name: image_policy reads
# RUN bodies, and `\bcurl\b` in a teardown is scored as a fetch (SBX-IMG-005).
# debian:bookworm-slim does not ship one; the builder that did is discarded.
RUN set -eux; \
    rm -rf /usr/bin/apt /usr/bin/apt-get /usr/bin/apt-cache /usr/bin/apt-key \
           /usr/bin/dpkg /usr/bin/dpkg-deb /usr/bin/dpkg-query; \
    rm -rf /etc/apt /var/lib/apt /var/lib/dpkg /var/cache/apt; \
    rm -rf /root/.netrc /root/.npmrc /root/.docker /usr/local/go

RUN set -eu; \
    fail=0; \
    for f in /usr/bin/apt-get /usr/bin/apt /usr/bin/dpkg \
             /usr/local/go /root/.netrc; do \
      if [ -e "$f" ]; then echo "SBX-IMG: $f survived into the enforcement image"; fail=1; fi; \
    done; \
    [ "$fail" -eq 0 ] || { \
      echo "the enforcement image ships a way to resolve a dependency at run time."; \
      echo "FR-021 requires it to ship resolved."; \
      exit 1; }; \
    echo "SBX-IMG: no package manager, index configuration or credential present"

USER 65534:65534

# Linux only, no degraded mode (OD-17). ServeEnforcement on F2A_PROXY_LISTEN.
CMD ["f2a-enforcement"]
