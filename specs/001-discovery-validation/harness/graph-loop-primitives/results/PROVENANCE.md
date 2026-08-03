# What is in here, and what is not

Three files. All three are **genuine raw artifacts recovered from the original run**,
not re-created, not transcribed, and not regenerated during recovery. They were copied
out of `/tmp/f2a-probe-runtime/` on 2026-08-02 with their content untouched.

| File | Produced by | What it is |
|---|---|---|
| `e6_side_effects.log` | `e6_p1d_midnode.py` | The `fsync`ed side-effect log from the crash-inside-a-node arm. 42 bytes, six lines, and it is character-for-character the block quoted in finding 006 §Primitive 1: `work:1, work:2, work:3, work:3, work:4, finish`. The duplicated `work:3` is the at-least-once result. |
| `e6_host_effects.log` | `e6_p5_hostloop.py` | The side-effect log from the hosted-inner-loop arm. 78 bytes, ten lines: four inner turns before the `SIGKILL`, then all four re-executed plus `inner:5` and `after`. This is the "**4 of 4** inner turns re-executed" measurement. |
| `e6_replay_snapshot.db` | `e6_p4_replay.py` | The post-crash SQLite session that primitive 4's four replays were driven from. **49,152 bytes, `sha256=11fa3ec869945b2419c7c34baaba80da70694d6be08099bedfad77c3816574f7`** — the `11fa3ec8…` the finding cites. Committing it is what makes that citation checkable. |

Verify the snapshot:

```bash
shasum -a 256 e6_replay_snapshot.db   # 11fa3ec8...
```

## What is missing

**No captured stdout from the original run exists.** The arms were driven
interactively and their verdict lines were transcribed into the finding from the
terminal. Nothing else survived, and nothing has been fabricated to fill the space —
the three files above are the complete set of surviving raw output.

The two `.log` files are append-only, so re-running the arms that produce them will
overwrite copies in the scratch directory, not these. These are read-only records.

None of these files contains a credential. They hold node tags, iteration counters,
and a session database whose only content is the string `"go"` and an iteration count.
