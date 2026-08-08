# T096 — the sandbox image. FR-021.
#
# The execution environment the agent's shell and general request capability
# (FR-004) run inside. Three properties, and the third is the one worth reading
# carefully.
#
#   1. A shell and a toolchain are present.
#   2. Every dependency is resolved and hash-pinned at build time.
#   3. **No package index is reachable — and this image is not what makes it
#      unreachable.**
#
# ## On (3), because it is the thing most likely to be built twice
#
# `research.md` §T-11 and `contracts/egress-policy.md` both record that FR-021
# and the egress policy are **one control**: resolving a dependency at run time
# is an outbound request to a destination that is not the target, so the
# enforcement point already denies it. Nothing in this file is a network
# control, and adding one — an iptables rule, a null-routed resolver, a proxy
# variable pointed at a black hole — would be a second mechanism for a
# requirement that already has one, described as defence in depth and behaving
# as two things to keep in agreement.
#
# What this file contributes is a different fact about the same requirement.
# The egress policy denies the *request*; this image removes the *means and the
# configuration to make it*. There is no `pip`, no `apt-get`, no index URL, no
# credential and no `.netrc` in the final stage. If the egress policy were
# somehow absent, a process here would not fail to reach an index — it would
# have nothing to reach one with. That is the shipping property FR-021 states
# ("MUST ship with its dependencies already resolved"), not a second
# enforcement of the denial clause.
#
# ## What makes the claim checkable rather than a comment
#
# Two things, neither of which is a comment:
#
#   - the `RUN` block at the end of the final stage **fails the build** if any
#     package manager, index configuration or credential file survived into the
#     image. A property asserted in a comment rots at the first edit; this one
#     is a build failure at the moment it stops being true;
#   - `src/sandbox/image_policy.py` reads this file and applies the same rules
#     statically, so CI checks them without a Docker daemon. Its findings are
#     asserted by `tests/invariants/test_sandbox_image.py`.
#
# ## Build
#
#   docker build -f deploy/images/sandbox.Dockerfile -t f2a-sandbox .
#
# It takes no `--build-arg` carrying a secret and no `--mount=type=secret`. A
# build that needed one would put it in a layer or in the build history, and
# "no secret" would then be a statement about the last layer only.

# --- builder ---------------------------------------------------------------
#
# Everything that needs a package manager happens here, and this stage is
# discarded. `pip` exists in the builder because resolving at *build* time is
# what FR-021 requires; it does not survive into the stage that ships.

FROM python:3.12-slim-bookworm AS builder

# FR-021 — resolved and hashed at build time. `--require-hashes` makes an
# unpinned addition to the lock file a build failure rather than a silent
# fetch of whatever the index is serving today.
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --prefix=/opt/deps \
      -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

# --- sandbox ---------------------------------------------------------------

FROM python:3.12-slim-bookworm AS sandbox

# The shell and the toolchain. `coreutils` and `bash` come from the base;
# `util-linux` and `procps` are what a shell session in a mount namespace needs
# to be diagnosable from inside. Installed and then torn down in one layer, so
# the package manager is not present in the shipped filesystem and is not
# recoverable from an earlier one either.
RUN apt-get update \
 && apt-get install -y --no-install-recommends util-linux procps \
 && rm -rf /var/lib/apt/lists/* \
 && apt-get purge -y --auto-remove apt-utils 2>/dev/null || true

COPY --from=builder /opt/deps /usr/local

# The teardown. Everything that could resolve a dependency at run time, and
# every place a credential or an index URL is conventionally read from.
#
# `pip` is removed rather than disabled: `PIP_NO_INDEX=1` is an environment
# variable, and an environment variable is a thing the process being contained
# can unset. The dependencies themselves stay — they were installed by the
# builder into /usr/local and are not managed by anything here.
RUN set -eux; \
    rm -rf /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12; \
    rm -rf /usr/local/lib/python3.12/site-packages/pip \
           /usr/local/lib/python3.12/site-packages/pip-*.dist-info; \
    rm -rf /usr/local/lib/python3.12/ensurepip; \
    rm -rf /usr/bin/apt /usr/bin/apt-get /usr/bin/apt-cache /usr/bin/apt-key \
           /usr/bin/dpkg /usr/bin/dpkg-deb /usr/bin/dpkg-query; \
    rm -rf /etc/apt /var/lib/apt /var/lib/dpkg /var/cache/apt; \
    rm -rf /etc/pip.conf /usr/pip.conf /root/.pip /root/.config/pip \
           /root/.netrc /root/.npmrc /root/.docker

# The build-time assertion. This is the mechanism, not the comments above it:
# if a later edit reinstates any of these, `docker build` fails here.
#
# It checks presence in the filesystem, which is a fact about the image. It
# does not attempt to reach a network, which would be a fact about the machine
# doing the build and would make the build's verdict depend on where it ran.
RUN set -eu; \
    fail=0; \
    for f in /usr/local/bin/pip /usr/local/bin/pip3 /usr/bin/apt-get \
             /usr/bin/apt /usr/bin/dpkg /etc/pip.conf /root/.netrc \
             /etc/apt/sources.list; do \
      if [ -e "$f" ]; then echo "SBX-IMG: $f survived into the sandbox image"; fail=1; fi; \
    done; \
    if python3 -c 'import pip' 2>/dev/null; then \
      echo "SBX-IMG: pip is importable in the sandbox image"; fail=1; \
    fi; \
    if [ -n "$(env | grep -Ei '^(PIP_INDEX_URL|PIP_EXTRA_INDEX_URL|NPM_TOKEN|PIP_TRUSTED_HOST)=' || true)" ]; then \
      echo "SBX-IMG: an index or credential variable is set in the image environment"; fail=1; \
    fi; \
    [ "$fail" -eq 0 ] || { \
      echo "the sandbox image ships a way to resolve a dependency at run time."; \
      echo "FR-021 requires it to ship resolved. See the header of this file"; \
      echo "for why the fix is removal here and not a network control."; \
      exit 1; }; \
    echo "SBX-IMG: no package manager, index configuration or credential present"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# An unprivileged identity for the contained process. The supervisor maps into
# this from the initial user namespace; it holds `CAP_SETUID`/`CAP_SETGID`
# there, so the mapping does not depend on this image granting anything.
RUN useradd --create-home --uid 10001 --shell /bin/bash agent
USER agent
WORKDIR /home/agent

# No ENTRYPOINT and no CMD. What runs here is what the supervisor executes
# under the session's mount namespace and seccomp filter; an entrypoint baked
# in would be a second answer to a question `src/supervisor/` already answers.
