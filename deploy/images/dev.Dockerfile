# T007 — the development image, **identical to the runtime image**.
#
# Finding 003 raised the toolchain question for a laptop: a developer's host
# has a different Python, a different libc and — on macOS — no Linux kernel at
# all. OD-17 makes the kernel facilities load-bearing, so a mechanism developed
# against a host that lacks them is a mechanism developed against nothing.
#
# The rule this file enforces is that there is one image. `runtime.Dockerfile`
# builds `FROM` the same base with the same lock file, so a toolchain question
# answered here is answered the same way in production. The development image
# adds test tooling and nothing else.
#
# Build and use:
#   docker build -f deploy/images/dev.Dockerfile -t f2a-dev .
#   docker run --rm --privileged -v "$PWD:/work" -w /work f2a-dev pytest -q
#
# `--privileged` is needed for the mount-namespace and cgroup tests and for
# nothing else. `tests/` marks those `@pytest.mark.privileged` so an
# unprivileged run skips them loudly rather than passing over them.

FROM python:3.12-slim-bookworm

# util-linux for `unshare`/`nsenter` when debugging a namespace by hand;
# procps for `/proc` tooling the bounds battery reads; strace is genuinely
# useful when a seccomp filter does not fire and guessing why is expensive.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      util-linux procps strace ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Go, for the enforcement point (Q-01).
#
# **Corrected 2026-08-08 under T096.** This block's comment said "pinned by
# version and checksum" and the block verified no checksum. The version was
# pinned and the bytes were whatever the download served, which is an unpinned
# toolchain download — dependency resolution at build time wearing a different
# name, and FR-021 does not distinguish. `src/sandbox/image_policy.py` reads
# this file and reports it as SBX-IMG-005.
#
# `GO_SHA256` has **no default**, so a build without one fails here and says
# so. A default would have to be a checksum for one version and one
# architecture, invented rather than observed, and an invented default that
# happens to match nothing is worse than the omission it replaces: it reads as
# verification and passes only where nobody looks.
ARG GO_VERSION=1.24.3
ARG TARGETARCH=arm64
ARG GO_SHA256
RUN set -eux; \
    if [ -z "${GO_SHA256:-}" ]; then \
      echo "GO_SHA256 is required: pass the checksum published for"; \
      echo "go${GO_VERSION}.linux-${TARGETARCH}.tar.gz at https://go.dev/dl/"; \
      echo "  docker build --build-arg GO_SHA256=<sha256> ..."; \
      exit 1; \
    fi; \
    url="https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz"; \
    curl -fsSL "$url" -o /tmp/go.tgz 2>/dev/null || \
      (apt-get update && apt-get install -y --no-install-recommends curl \
       && rm -rf /var/lib/apt/lists/* && curl -fsSL "$url" -o /tmp/go.tgz); \
    echo "${GO_SHA256}  /tmp/go.tgz" | sha256sum -c -; \
    tar -C /usr/local -xzf /tmp/go.tgz; \
    rm /tmp/go.tgz
ENV PATH="/usr/local/go/bin:${PATH}" \
    GOFLAGS="-mod=mod" \
    CGO_ENABLED=0

# FR-021 — every dependency resolved and hashed at build time. `--require-hashes`
# is implied by the presence of hashes in the lock file and makes an unpinned
# addition a build failure rather than a silent fetch.
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

# Nothing is resolved at run time. The runtime image drops the toolchain and
# the test tooling; the egress policy denies the package index either way, so
# this is one control stated twice rather than two mechanisms.
ENV PIP_NO_INDEX=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/work

WORKDIR /work
