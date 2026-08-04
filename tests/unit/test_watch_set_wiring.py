"""The seccomp watch set, and the three things that have to be true together
before a syscall in it produces an honest record.

Finding 021 measured ten ordinary writes under the real listener inside a
declared read-only location. Six produced a `filesystem_decision` and **four
produced nothing at all** — `os.rename`, `os.symlink`, `os.link`, `os.utime`.
The watch set contains `renameat2`; glibc issues `renameat`. It contains the
newer syscall and misses the one the platform's own C library calls.

**The interesting part is not the omission, it is that adding the name back is
not a fix.** Three tables have to agree before a watched syscall records
anything true:

| table | lives in | what a missing entry produces |
|---|---|---|
| `path_taking_syscalls()` | `_linux.py` | no notification at all — silence |
| `_PATH_ARG` | `seccomp.py` | `path=None`, so `decide()` returns **FS-005** |
| `WRITE_SYSCALLS` | `fs_decisions.py` | `modifies` is false, so `decide()` **allows** |

Measured against the real listener on `6.12.76-linuxkit`/`aarch64`, adding
`renameat` to the watch set and nothing else:

    as shipped                              no record at all
    watched, no _PATH_ARG                   deny FS-005 path_unreadable_at_notification
    watched, _PATH_ARG=1, WRITE_SYSCALLS    allow  rule_id=None  mode='ro'
    unchanged

The third is the worst of the three. FS-005 asserts *the path could not be read
out of the target* about a path that was never looked for; an `allow` asserts
the rename was permitted, which is defect X4 — the one `is_write_open` exists to
have fixed — resurrected for four more syscalls. **Silence undercounts; both
partial states misreport.** So the tests here hold the watch set to being
completely wired rather than merely larger, and `install_filter` refuses a
partial one.

**All three tables now name the four**, so the watch set contains them and the
`xfail` that held the middle test is gone. What survives the fix is the shape:
the three invariants below are about any future addition, not about these four,
and `check_watch_set_is_wired` is what enforces them on a watch set supplied at
runtime through `syscalls=`.
"""

from __future__ import annotations

import pytest

from src.supervisor import _linux, fs_decisions, seccomp

# The listener's own statement of which watched syscalls cannot modify.
# Imported rather than restated here: a second copy would let the two drift,
# and the guard would then be checked against a list no longer used.
NON_MODIFYING = seccomp.NON_MODIFYING_SYSCALLS

ARCHITECTURES = ("x86_64", "aarch64")


def watch_set_for(arch: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """`path_taking_syscalls()` as it resolves on `arch`, from the tables alone.

    Both architecture tables are checked on whatever host runs the suite. This
    is a pure data read with nothing executed, so it is not subject to the
    `qemu-user` artifacts that made finding 021 discard its x86_64 *liveness*
    column — a number in a table is a number in a table.
    """
    monkeypatch.setattr(_linux, "machine", lambda: arch)
    return _linux.path_taking_syscalls()


# --- what ordinary library calls actually issue ---------------------------

# Measured with `strace -e trace=%file` under CPython 3.12 on
# `6.12.76-linuxkit`/`aarch64`:
#
#   os.rename  -> renameat(AT_FDCWD, old, AT_FDCWD, new)
#   os.symlink -> symlinkat(target, AT_FDCWD, linkpath)
#   os.link    -> linkat(AT_FDCWD, old, AT_FDCWD, new, 0)
#   os.utime   -> utimensat(AT_FDCWD, path, times, flags)
#
# CPython's own import machinery issues `renameat` too, writing bytecode caches
# into place — so this is not only reachable by workload code.
ORDINARY_WRITE_SYSCALLS = ("renameat", "symlinkat", "linkat", "utimensat")

# Derived from one authoritative header per architecture, never by
# concatenating several:
#   x86_64   /usr/include/x86_64-linux-gnu/asm/unistd_64.h  (debian bookworm)
#   aarch64  /usr/include/asm-generic/unistd.h              (debian bookworm)
# `renameat` on aarch64 sits behind `#ifdef __ARCH_WANT_RENAMEAT`, which
# `/usr/include/aarch64-linux-gnu/asm/unistd.h` defines, so it is present.
NUMBERS_FROM_SOURCE = {
    "x86_64": {"renameat": 264, "symlinkat": 266, "linkat": 265,
               "utimensat": 280},
    "aarch64": {"renameat": 38, "symlinkat": 36, "linkat": 37,
                "utimensat": 88},
}


@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_both_tables_carry_the_numbers_for_ordinary_write_syscalls(arch) -> None:
    """The numbers, before anything is watched.

    Recorded first and separately from the watch set because a number is a
    fact about the ABI and watching is a decision about the mechanism. Getting
    the number wrong is how a filter silently matches something else — finding
    021 records a probe that read `94` as `lchown` when it was `exit_group`.
    """
    table = _linux._SYSCALL_NUMBERS[arch]
    missing = {
        name: expected
        for name, expected in NUMBERS_FROM_SOURCE[arch].items()
        if table.get(name) != expected
    }
    assert not missing, (
        f"{arch} table is missing or disagrees on {missing}; these are the "
        "syscalls os.rename, os.symlink, os.link and os.utime issue"
    )


# The `xfail(strict=True)` that used to stand here is gone, which is the whole
# of what "unblocked" means: `fs_decisions.WRITE_SYSCALLS` names all four, so
# `path_taking_syscalls()` can watch them without `decide()` recording an
# `allow`. The marker was strict precisely so that landing the fix and leaving
# the marker would fail the suite rather than pass quietly.
@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_the_watch_set_covers_what_ordinary_python_writes_issue(
    arch, monkeypatch
) -> None:
    watched = watch_set_for(arch, monkeypatch)
    unwatched = [n for n in ORDINARY_WRITE_SYSCALLS if n not in watched]
    assert not unwatched, (
        f"on {arch} the watch set does not contain {unwatched}. Finding 021 "
        "measured four ordinary writes producing no filesystem_decision at "
        "all inside a declared read-only location."
    )


# --- the wiring invariants: all three tables agree ------------------------


@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_every_watched_syscall_has_a_path_argument_index(arch, monkeypatch) -> None:
    """Without this, a watch-set addition produces FS-005 instead of silence.

    `NotificationListener` builds `self._path_arg` by intersecting the watch
    set with `_PATH_ARG`, so a watched syscall absent from the map yields
    `path=None`, and `decide()` tests `path is None` first. The record then
    says the path could not be read out of the target, about a path the
    listener never went looking for.
    """
    watched = watch_set_for(arch, monkeypatch)
    unmapped = sorted(n for n in watched if n not in seccomp._PATH_ARG)
    assert not unmapped, (
        f"on {arch}, {unmapped} are watched with no _PATH_ARG entry; each "
        "would be recorded as FS-005 path_unreadable_at_notification"
    )


@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_every_watched_syscall_can_be_classified(arch, monkeypatch) -> None:
    """Without this, a watch-set addition produces an `allow`.

    `decide()` computes `modifies` from `WRITE_SYSCALLS` and `OPEN_SYSCALLS`.
    A watched syscall in neither, and not on the enumerated read-only list, is
    a write the classifier will wave through with `rule_id=None`.
    """
    watched = watch_set_for(arch, monkeypatch)
    known = (fs_decisions.WRITE_SYSCALLS | fs_decisions.OPEN_SYSCALLS
             | NON_MODIFYING)
    unclassifiable = sorted(n for n in watched if n not in known)
    assert not unclassifiable, (
        f"on {arch}, {unclassifiable} are watched and appear in neither "
        "fs_decisions.WRITE_SYSCALLS nor OPEN_SYSCALLS nor the enumerated "
        "read-only set, so decide() would record an allow for them"
    )


@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_the_read_only_list_names_nothing_that_can_modify(arch, monkeypatch) -> None:
    """The enumerated read-only set is an assertion, so it is checked.

    A name in both `NON_MODIFYING` and `WRITE_SYSCALLS` would let the
    classifiability test above pass for a syscall that modifies.
    """
    overlap = sorted(NON_MODIFYING & fs_decisions.WRITE_SYSCALLS)
    assert not overlap, f"{overlap} are listed as non-modifying and as writes"
    assert not sorted(NON_MODIFYING & fs_decisions.OPEN_SYSCALLS)


def test_a_null_path_utimensat_is_recorded_as_unreadable() -> None:
    """The one watched syscall whose path argument may legally be NULL.

    `futimens(fd, times)` is `utimensat(fd, NULL, times, 0)` and operates on
    the descriptor, so there is no path to read and `read_target_path` returns
    None. Measured under the real listener on `6.12.76-linuxkit`/`aarch64`:
    `deny`, `FS-005`, `mode='absent'`, `path=None`.

    Pinned rather than fixed. `deny` is the conservative disposition and is
    what SC-022 counts; the imprecision is in the *reason*, which says the
    path could not be read when there was none to read. Separating those needs
    a new rule identifier, which every emitted record would carry — an owner
    decision rather than part of wiring four syscalls up. Asserted here so it
    is a known property with a test naming it, not a surprise in an audit.
    """
    from src.supervisor.location_set import parse

    location_set = parse({
        "schema_version": "1.0.0", "set_version": "1", "deployment_id": "t",
        "locations": [{"source": "/ro", "target": "/ro", "mode": "ro",
                       "rule_id": "FS-DECL", "justification": "the ro arm"}],
    })
    decision = fs_decisions.decide(
        location_set, session_id="s", syscall="utimensat", path=None,
        pid=1, flags=None,
    )
    assert decision.disposition == fs_decisions.DENY
    assert decision.rule_id == fs_decisions.UNREADABLE_PATH.rule_id
    assert decision.mode == "absent"


# --- the guard: a partial watch set is refused ----------------------------


def test_installing_a_filter_for_an_unmapped_syscall_is_refused() -> None:
    """The structural fix for "adding to the watch set is not sufficient".

    Refused at filter-install time rather than caught by a test, because the
    watch set is a parameter — `spawn_with_listener(..., syscalls=...)` accepts
    an arbitrary one, and that is the API finding 021's counterfactual arm used
    to add `openat2` without editing a source file. A caller can therefore
    reach the misreporting state at runtime, with no source edit for a test to
    notice.
    """
    with pytest.raises(seccomp.SeccompError) as exc:
        seccomp.check_watch_set_is_wired({"openat": 56, "openat2": 437})
    assert "openat2" in str(exc.value)
    assert "_PATH_ARG" in str(exc.value)


def test_installing_a_filter_for_an_unclassifiable_syscall_is_refused() -> None:
    """The second half of the guard, asserted separately.

    A syscall can have a path index and still be unclassifiable, which is the
    arm that records an `allow`. Both halves are checked because a guard that
    covered only `_PATH_ARG` would let the worse of the two states through.

    **This test used `renameat` and had to be changed, which is the hazard it
    exists for.** Once `WRITE_SYSCALLS` named `renameat`, the guard correctly
    stopped refusing it and this assertion started failing — loudly, which is
    the good case. The bad case is the one to guard against: had the example
    been a name that quietly became classifiable, the test would have kept
    passing while asserting nothing. So the example is now `mknodat`, taken
    from `KNOWINGLY_UNWATCHED` above, and
    `test_the_unclassifiable_example_is_still_unclassifiable` below fails the
    day that stops being true rather than letting this go vacuous.
    """
    with pytest.raises(seccomp.SeccompError) as exc:
        seccomp.check_watch_set_is_wired(
            # mknodat(dirfd, pathname, mode, dev) -> pathname is index 1.
            {"openat": 56, "mknodat": 33},
            path_arg={**seccomp._PATH_ARG, "mknodat": 1},
        )
    assert "mknodat" in str(exc.value)
    assert "WRITE_SYSCALLS" in str(exc.value)


def test_the_unclassifiable_example_is_still_unclassifiable() -> None:
    """Keeps the test above from passing over nothing.

    `pytest.raises` is satisfied by *any* `SeccompError`, so if `mknodat` were
    later classified the test above would still pass — on the `_PATH_ARG` arm,
    for a name it supplies an index for. It asserts `"WRITE_SYSCALLS"` in the
    message to make that specific, and this states the precondition directly.
    """
    classified = (fs_decisions.WRITE_SYSCALLS | fs_decisions.OPEN_SYSCALLS
                  | NON_MODIFYING)
    assert "mknodat" not in classified, (
        "mknodat is now classified, so it can no longer demonstrate the "
        "guard's second arm. Pick another name from KNOWINGLY_UNWATCHED that "
        "is in none of WRITE_SYSCALLS, OPEN_SYSCALLS or NON_MODIFYING."
    )


def test_the_second_arm_cannot_fire_through_the_shipped_tables() -> None:
    """Stated rather than left to be discovered, because it reads as a bug.

    Every name in `_PATH_ARG` is now classified, so a caller who supplies only
    `syscalls=` — which is all `spawn_with_listener` and `install_filter`
    permit — can never reach the second arm: anything that passes the
    `_PATH_ARG` check is classifiable by construction. The arm is not dead
    code, it is the check on the *next* `_PATH_ARG` entry, and the two tests
    above exercise it through the `path_arg` override for exactly that reason.

    Pinned so that a future `_PATH_ARG` addition with no classification turns
    this red and has to be resolved deliberately.
    """
    classified = (fs_decisions.WRITE_SYSCALLS | fs_decisions.OPEN_SYSCALLS
                  | NON_MODIFYING)
    unclassified = sorted(n for n in seccomp._PATH_ARG if n not in classified)
    assert not unclassified, (
        f"{unclassified} have a _PATH_ARG index and no classification. That "
        "is reachable at runtime through syscalls= alone, and decide() would "
        "record an allow. Add each to fs_decisions.WRITE_SYSCALLS, "
        "OPEN_SYSCALLS, or seccomp.NON_MODIFYING_SYSCALLS."
    )


def test_the_shipped_watch_set_passes_its_own_guard() -> None:
    """So the guard is not trivially satisfiable by being unreachable."""
    seccomp.check_watch_set_is_wired(_linux.path_taking_syscalls())


# The two tests above check that the guard *says no*. These three check that
# anything actually asks it. A guard function nothing calls passes every test
# written about the function and defends nothing — which is the same shape as
# the FS-002 rule that "sat in the registry unreached for its whole life".
#
# All three entry points reject before touching the kernel, so all three are
# exercised on any host, including the macOS one where the privileged suite is
# deselected.
#
# **There were two of these and there are three, and the third was found by
# measurement rather than by reading.** `check_watch_set_is_wired` has three
# call sites; only `install_filter` and `spawn_with_listener` were covered.
# Deleting the call from `NotificationListener.__init__` and running the whole
# suite privileged on `6.12.76-linuxkit`/`aarch64` gave **505 passed, 1
# skipped** — the guard's third call site removed, and not one assertion in the
# repository noticed. That is the defect this block's own comment describes,
# sitting inside the block that describes it.


def test_install_filter_asks_the_guard_before_touching_the_kernel() -> None:
    with pytest.raises(seccomp.SeccompError) as exc:
        seccomp.install_filter({"openat": 56, "openat2": 437})
    assert "_PATH_ARG" in str(exc.value), (
        "install_filter failed for some other reason, so this does not show "
        "that it consults the guard"
    )


def test_spawn_with_listener_asks_the_guard_before_forking() -> None:
    """Checked separately because the child cannot report why it died.

    `install_filter` runs in the forked child, whose only channel is
    `os._exit(126)`. If `spawn_with_listener` did not check before the fork,
    the parent would raise "the child did not hand over a notification fd" and
    the actual reason would be gone.
    """
    with pytest.raises(seccomp.SeccompError) as exc:
        seccomp.spawn_with_listener(
            ["/bin/true"], lambda _a: None, {"openat": 56, "openat2": 437}
        )
    assert "_PATH_ARG" in str(exc.value), (
        f"spawn_with_listener raised {exc.value!r} rather than the guard's "
        "message, so the check is happening after the fork if at all"
    )


def test_the_listener_asks_the_guard_before_reading_any_notification() -> None:
    """The third call site, which is reachable without either of the other two.

    `NotificationListener(fd, on_attempt, syscalls=...)` is constructible on
    its own — the class's own docstring says the wiring check is repeated here
    "rather than assumed to have run" — so a caller that builds a listener over
    a descriptor it obtained some other way reaches the misreporting state with
    neither `install_filter` nor `spawn_with_listener` involved.

    The guard runs before `notif_sizes()`, so this needs no descriptor and no
    kernel: `fd=-1` is never touched. That is what makes the assertion cheap
    enough to run everywhere, and it is also the reason the omission was
    invisible — nothing about the gap looked like a platform limitation.
    """
    with pytest.raises(seccomp.SeccompError) as exc:
        seccomp.NotificationListener(-1, lambda _a: None, {"openat": 56, "openat2": 437})
    assert "_PATH_ARG" in str(exc.value), (
        f"NotificationListener raised {exc.value!r} rather than the guard's "
        "message, so it is not consulting the guard before it starts "
        "answering notifications"
    )


# --- the subset is named rather than implied ------------------------------

# Finding 021's honest framing of the leave-it-alone option: not "document
# `openat2`" but "document that the watch set is a named subset, and state the
# subset" — because a reader of the contract would otherwise infer that
# `openat2` is the exception rather than one of twelve.
KNOWINGLY_UNWATCHED = {
    "openat2": "third argument is a pointer to struct open_how, not a flag "
               "word; reading it reintroduces the TOCTOU on a value the "
               "classifier acts on. Owner decision, still open.",
    "creat": "x86_64 only; has an _IMPLIED_FLAGS entry ready for the day it "
             "is watched.",
    "mknodat": "not yet costed",
    "fchownat": "not yet costed",
    "fchmodat2": "not yet costed; absent from bookworm headers",
    "setxattr": "not yet costed",
    "lsetxattr": "not yet costed",
    "removexattr": "not yet costed",
    "lremovexattr": "not yet costed",
    "symlink": "x86_64 only; not yet costed",
    "link": "x86_64 only; not yet costed",
    "utime": "x86_64 only; not yet costed",
    "utimes": "x86_64 only; not yet costed",
    "futimesat": "x86_64 only; not yet costed",
    "mknod": "x86_64 only; not yet costed",
}


# The watch set as it stands, per architecture. Pinned because **nothing in
# the suite stated it before**, and that is the whole of why defect 1 survived:
# `test_the_filter_covers_the_path_taking_set` asserts `"openat" in watched` and
# then that the compiled program is `4 + len(set(watched.values())) + 2`
# instructions long — an expectation re-derived from `watched` itself, and
# therefore true of any watch set at all. Measured: deleting `fchmodat` from
# `path_taking_syscalls()` and running the full privileged suite gave
# 464 passed, 0 related failures.
#
# A test that pins a set is normally a maintenance tax. Here it is the
# instrument: a watch set is a security surface, and every change to one should
# cost the person making it a deliberate edit in a file that says why.
WATCH_SET = {
    "aarch64": {
        "chdir", "faccessat", "faccessat2", "fchmodat", "mkdirat",
        "newfstatat", "openat", "readlinkat", "renameat2", "statx",
        "truncate", "unlinkat",
        # Added when WRITE_SYSCALLS unblocked them.
        "linkat", "renameat", "symlinkat", "utimensat",
    },
    "x86_64": {
        "access", "chdir", "chmod", "faccessat", "faccessat2", "fchmodat",
        "lstat", "mkdir", "mkdirat", "newfstatat", "open", "openat",
        "readlink", "readlinkat", "rename", "renameat2", "stat", "statx",
        "truncate", "unlink", "unlinkat",
        "linkat", "renameat", "symlinkat", "utimensat",
    },
}


@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_the_watch_set_is_exactly_what_is_written_down(arch, monkeypatch) -> None:
    observed = set(watch_set_for(arch, monkeypatch))
    expected = WATCH_SET[arch]
    assert observed == expected, (
        f"on {arch} the watch set changed.\n"
        f"  added:   {sorted(observed - expected)}\n"
        f"  removed: {sorted(expected - observed)}\n"
        "Update WATCH_SET here, and if a name was added make sure it also has "
        "a `_PATH_ARG` index and a `fs_decisions` classification — "
        "`check_watch_set_is_wired` will refuse the session otherwise."
    )


@pytest.mark.parametrize("arch", ARCHITECTURES)
def test_nothing_is_both_watched_and_declared_unwatched(arch, monkeypatch) -> None:
    """The subset statement above has to stay true as the watch set moves.

    If a name here is later watched, this fails and the entry has to be
    removed — so the list cannot rot into a description of a set it no longer
    describes, which is how `openat2` came to look like the sole exception.
    """
    watched = watch_set_for(arch, monkeypatch)
    contradictions = sorted(set(watched) & set(KNOWINGLY_UNWATCHED))
    assert not contradictions, (
        f"on {arch}, {contradictions} are watched and also listed as "
        "knowingly unwatched; remove them from KNOWINGLY_UNWATCHED"
    )
