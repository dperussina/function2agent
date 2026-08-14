# T159 — the analysis image. Linux only, no degraded mode (OD-17).
#
# Residual, named rather than papered over: `src/analysis/` has no `def main`.
# Analysis is a stage, not a daemon. This image does not invent a serve loop
# (OD-36). `F2A_ANALYSIS_ENTRY` selects a documented module (`python -m …`)
# when one exists; unset, the process fails loud and starts nothing.
#
# `codegraph` is invoked as a subprocess at analysis time only (T119, T-11)
# and is a git-ignored vendored tree (`examples/codegraph`). This image does
# not bundle a JavaScript toolchain: there is no committed binary to COPY, and
# resolving one at run time is FR-021. An operator who has built the pin
# mounts it and sets PATH.
#
# Holds neither credential plane (FR-036). `image_policy.py` walks this file.
#
# Build:
#   docker build -f deploy/images/analysis.Dockerfile -t f2a-analysis .

FROM python:3.12-slim-bookworm AS builder

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --prefix=/opt/deps \
      -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

FROM python:3.12-slim-bookworm AS analysis

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
      if [ -e "$f" ]; then echo "SBX-IMG: $f survived into the analysis image"; fail=1; fi; \
    done; \
    if python3 -c 'import pip' 2>/dev/null; then \
      echo "SBX-IMG: pip is importable in the analysis image"; fail=1; \
    fi; \
    if [ -n "$(env | grep -Ei '^(PIP_INDEX_URL|PIP_EXTRA_INDEX_URL|NPM_TOKEN|PIP_TRUSTED_HOST)=' || true)" ]; then \
      echo "SBX-IMG: an index or credential variable is set in the image environment"; fail=1; \
    fi; \
    [ "$fail" -eq 0 ] || { \
      echo "the analysis image ships a way to resolve a dependency at run time."; \
      echo "FR-021 requires it to ship resolved."; \
      exit 1; }; \
    echo "SBX-IMG: no package manager, index configuration or credential present"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/f2a \
    F2A_ANALYSIS_ENTRY=

WORKDIR /opt/f2a
USER 65534:65534

# Fail loud when no analysis process exists to start. Linux only, no degraded
# mode (OD-17).
CMD ["sh", "-c", "if [ -z \"${F2A_ANALYSIS_ENTRY}\" ]; then echo 'analysis image: no process to start. src/analysis/ has no def main; analysis is a stage, not a daemon (OD-36). F2A_ANALYSIS_ENTRY is unset. Linux only, no degraded mode (OD-17).'; exit 1; fi; exec python -m \"${F2A_ANALYSIS_ENTRY}\""]
