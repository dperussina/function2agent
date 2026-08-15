# T159 — the supervisor image. Linux only, no degraded mode (OD-17).
#
# Process: `python -m src.supervisor.main`. OD-36 ⑤ still holds:
# report+exit after opening SessionTable. Darwin refuses at preflight.
# No serve loop is invented here.
#
# This image is where a second writer on the session store first becomes
# possible. T016's SessionTable → Repository migration is closed (session_table
# sits on Repository; finding 033's race measured 8 of 12 losers before and
# 0 of 12 after). The remaining limb — the store created once before any
# second process attaches — is asserted by the compose bundle (T160), not by
# silently re-migrating this image.
#
# FR-021: same builder/lock/teardown shape as runtime.Dockerfile.
# `image_policy.py` walks this file.
#
# Runs as root in the initial user namespace: OD-29 permits CAP_SETUID /
# CAP_SETGID there so the uid map can be written. The sandbox image is the
# one that drops to uid 10001.
#
# Build:
#   docker build -f deploy/images/supervisor.Dockerfile -t f2a-supervisor .

FROM python:3.12-slim-bookworm AS builder

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --prefix=/opt/deps \
      -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

FROM python:3.12-slim-bookworm AS supervisor

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
      if [ -e "$f" ]; then echo "SBX-IMG: $f survived into the supervisor image"; fail=1; fi; \
    done; \
    if python3 -c 'import pip' 2>/dev/null; then \
      echo "SBX-IMG: pip is importable in the supervisor image"; fail=1; \
    fi; \
    if [ -n "$(env | grep -Ei '^(PIP_INDEX_URL|PIP_EXTRA_INDEX_URL|NPM_TOKEN|PIP_TRUSTED_HOST)=' || true)" ]; then \
      echo "SBX-IMG: an index or credential variable is set in the image environment"; fail=1; \
    fi; \
    [ "$fail" -eq 0 ] || { \
      echo "the supervisor image ships a way to resolve a dependency at run time."; \
      echo "FR-021 requires it to ship resolved."; \
      exit 1; }; \
    echo "SBX-IMG: no package manager, index configuration or credential present"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/f2a

WORKDIR /opt/f2a

# OD-36 ⑤: report+exit after opening SessionTable. Linux only, no
# degraded mode (OD-17).
CMD ["python", "-m", "src.supervisor.main"]
