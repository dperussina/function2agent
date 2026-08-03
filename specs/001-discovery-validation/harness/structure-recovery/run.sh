#!/usr/bin/env bash
#
# E1 — structure recovery. Runs the recovered queries in queries.sql against a
# codegraph index, read-only.
#
# THIS CANNOT REPRODUCE FINDING 001. The target is a private production monorepo
# that is deliberately not vendored, so there is no index to point this at that
# would return the finding's numbers. Read README.md before running it: what is
# committed here is an inspectable method, not a reproducible measurement.
#
# Against some other codegraph index it will run and return that index's own
# numbers, which are not comparable to anything in finding 001.
#
# Usage:
#   ./run.sh /path/to/.codegraph/codegraph.db [subproject-dir]
#   CODEGRAPH_DB=/path/to/codegraph.db ./run.sh
#
# The subproject argument scopes blocks 5 and 6's second query to one top-level
# directory. The original ran against a directory inside a private repository;
# its name is not committed. Omit it and those blocks return nothing rather than
# guessing at a directory that may not exist in your index.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="${1:-${CODEGRAPH_DB:-}}"
SUBPROJECT="${2:-${CODEGRAPH_SUBPROJECT:-}}"

if [ -z "$DB" ]; then
  cat >&2 <<'EOF'
No codegraph index given.

  ./run.sh /path/to/.codegraph/codegraph.db [subproject-dir]
  CODEGRAPH_DB=/path/to/codegraph.db ./run.sh

There is no default, and there is deliberately no bundled target: finding 001
measured a private monorepo that is not vendored and not copied. The index is
opened read-only and nothing is written to it or to the repository it describes.
EOF
  exit 2
fi

[ -e "$DB" ] || { echo "no index at $DB" >&2; exit 1; }

if [ -z "$SUBPROJECT" ]; then
  echo "note: no subproject given — the per-subproject blocks will return nothing." >&2
fi

# mode=ro is the whole safety story here: the query set only reads structural
# columns, and the connection cannot write even if one of them were wrong.
case "$DB" in
  /*) URI="file://${DB}?mode=ro" ;;
  *)  URI="file:$(cd "$(dirname "$DB")" && pwd)/$(basename "$DB")?mode=ro" ;;
esac

{
  printf '.parameter init\n'
  printf ".parameter set :subproject '%s'\n" "$SUBPROJECT"
  printf '.headers on\n.mode column\n'
  printf ".read %s\n" "$HERE/queries.sql"
} | sqlite3 "$URI"
