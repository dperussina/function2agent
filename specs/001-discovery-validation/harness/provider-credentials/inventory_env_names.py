"""List the *names* of every variable defined in a tree's dotenv files.

Names only. This script never holds a value in a variable that outlives the line
that parsed it, never prints one, and never writes one. It exists so the
reconnaissance step behind finding 002's credential-discovery section can be
re-run locally instead of shipping one machine's inventory in this repository.

The original run of this step left `/tmp/f2a_keynames.txt` (153 names). That file
is deliberately *not* committed: it is an inventory of a private production
repository's environment-variable naming, it is worthless outside that machine,
and regenerating it here is strictly more reproducible. See the README.

Usage:  python3 inventory_env_names.py --env-root PATH
        F2A_ENV_ROOT=PATH python3 inventory_env_names.py [--by-file]
"""
import os
import sys

import envroot

ROOT = envroot.resolve()
BY_FILE = "--by-file" in sys.argv

names: set[str] = set()
per_file: dict[str, list[str]] = {}

for path in envroot.find_env_files(ROOT):
    # parse() returns name -> value; the values are discarded on the next line
    # and never enter any other structure.
    file_names = sorted(envroot.parse(path).keys())
    if file_names:
        per_file[os.path.relpath(path, ROOT)] = file_names
    names.update(file_names)

print(f"scan root       : {ROOT}")
print(f"dotenv files    : {len(per_file)}")
print(f"distinct names  : {len(names)}")

if BY_FILE:
    for rel in sorted(per_file):
        print(f"\n{rel}")
        for n in per_file[rel]:
            print(f"  {n}")
else:
    print()
    for n in sorted(names):
        print(n)
