# T159 — the runtime image. Linux only, no degraded mode (OD-17).
#
# T007's rule: there is one image. This file builds FROM the same base as
# `dev.Dockerfile` with the same lock file, so a toolchain question answered
# there is answered the same way here. The development image adds test tooling
# and nothing else; this one drops the toolchain and the test tooling.
#
# Process: `python -m src.runtime.main`. T215: admits, constructs a
# Registry, and binds via build_server. No longer report+exit. Supervisor
# still is (OD-36 ⑤). No serve loop is invented here.
#
# FR-021: dependencies resolved from the hash-pinned lock in a builder stage.
# The shipped stage has no package manager, no index, no credential, no
# `.netrc`. A new final-stage pip/apt/curl is a finding — `image_policy.py`
# walks this file (checked, not assumed).
#
# Build:
#   docker build -f deploy/images/runtime.Dockerfile -t f2a-runtime .

FROM python:3.12-slim-bookworm AS builder

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --prefix=/opt/deps \
      -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

FROM python:3.12-slim-bookworm AS runtime

COPY --from=builder /opt/deps /usr/local
COPY src /opt/f2a/src
COPY pyproject.toml /opt/f2a/pyproject.toml

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

RUN set -eu; \
    fail=0; \
    for f in /usr/local/bin/pip /usr/local/bin/pip3 /usr/bin/apt-get \
             /usr/bin/apt /usr/bin/dpkg /etc/pip.conf /root/.netrc \
             /etc/apt/sources.list; do \
      if [ -e "$f" ]; then echo "SBX-IMG: $f survived into the runtime image"; fail=1; fi; \
    done; \
    if python3 -c 'import pip' 2>/dev/null; then \
      echo "SBX-IMG: pip is importable in the runtime image"; fail=1; \
    fi; \
    if [ -n "$(env | grep -Ei '^(PIP_INDEX_URL|PIP_EXTRA_INDEX_URL|NPM_TOKEN|PIP_TRUSTED_HOST)=' || true)" ]; then \
      echo "SBX-IMG: an index or credential variable is set in the image environment"; fail=1; \
    fi; \
    [ "$fail" -eq 0 ] || { \
      echo "the runtime image ships a way to resolve a dependency at run time."; \
      echo "FR-021 requires it to ship resolved."; \
      exit 1; }; \
    echo "SBX-IMG: no package manager, index configuration or credential present"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/f2a

WORKDIR /opt/f2a
USER 65534:65534

# T215: binds via build_server. Linux only, no degraded mode (OD-17).
CMD ["python", "-m", "src.runtime.main"]
