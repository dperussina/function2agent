"""RECONSTRUCTED, NOT RECOVERED. Counts provider-opaque reasoning fields in ADK's
LiteLlm adapter.

WHAT THIS COUNTS, PLAINLY: **the number of source lines that contain the
identifier** — what `grep -c` reports — in the single module
`google/adk/models/lite_llm.py`, at the pinned `google-adk==2.6.1`. A line
mentioning a field twice counts once. That rule, and only that rule, reproduces
finding 003 result 7's four integers.

Finding 003 result 7 words them as "references `thought_signature` 35 times".
Read literally that means occurrences, which is 38. The finding carries a
correction, dated 2026-08-02, recording that its figures are line counts and
that "on 35 lines of" is the accurate phrasing. Three rules, three answers,
against the pin:

    rule                              thought_ thinking_ reasoning_ encrypted_
                                     signature  blocks    content    content
    source lines containing it   ->      35       16          9          0   <- reported
    textual occurrences          ->      38       18         11          0
    whole-word occurrences       ->      30       17         11          0

The whole-word column is lower for `thought_signature` because seven lines
mention it only inside the longer names `_decode_thought_signature` and
`_extract_thought_signature_from_tool_call`.

**Why the line rule and not another.** The original script did not survive and
the finding records the integers without the method, so the rule was chosen by
testing candidates against the reported values. The line rule matches all four
exactly; neither other rule matches any of the three non-zero ones. That is an
inference **fitted to the very numbers it is meant to reproduce**, not an
independent validation — one rule matching four integers with no free parameters
is strong evidence, and it is not the same thing as holding the original script.
All three columns are printed below so the choice stays visible rather than
baked in.

The load-bearing half of result 7 does not depend on any of this:
`encrypted_content` is xAI's opaque reasoning field, the claim is that it appears
**zero** times in this adapter, and zero is zero under every rule. Note the
scope: `google-adk` 2.6.1 does reference `encrypted_content` in
`google/adk/labs/openai/_openai_responses_llm.py`. Result 7 is about the LiteLlm
path, and this script only ever reads that one module.

Counts are against `google-adk==2.6.1`. They will drift on any other version, so
a mismatch on a different pin means the adapter changed, not that the finding was
wrong.

Usage:  python3 count_reasoning_fields.py
"""
import importlib.util
import pathlib
import re
import sys

# field -> the integer finding 003 result 7 reports
FIELDS = {
    "thought_signature": 35,
    "thinking_blocks": 16,
    "reasoning_content": 9,
    "encrypted_content": 0,
}

PINNED_ADK = "2.6.1"


def locate():
    spec = importlib.util.find_spec("google.adk.models.lite_llm")
    if spec is None or not spec.origin:
        sys.exit(
            "google.adk.models.lite_llm not importable.\n"
            "  Activate the harness virtualenv first — see the README."
        )
    return pathlib.Path(spec.origin)


def adk_version():
    try:
        from importlib.metadata import version

        return version("google-adk")
    except Exception:  # noqa: BLE001
        return "unknown"


def count_lines(text, needle):
    """Matching lines — the `grep -c` rule. THIS is the reported rule."""
    return sum(1 for line in text.splitlines() if needle in line)


def count_occurrences(text, needle):
    """Every textual appearance, including inside longer identifiers."""
    return len(re.findall(re.escape(needle), text))


def count_whole_word(text, needle):
    """Appearances as a standalone identifier, excluding longer names."""
    return len(re.findall(r"\b" + re.escape(needle) + r"\b", text))


adapter = locate()
text = adapter.read_text(encoding="utf-8", errors="ignore")
found_version = adk_version()

print(f"adapter     : {adapter}")
print(f"google-adk  : {found_version} (finding 003 measured {PINNED_ADK})")
if found_version not in (PINNED_ADK, "unknown"):
    print("  NOTE: version differs from the pin; counts below are not comparable.")
print()
print("LINES is the reported rule; the other two columns are shown for contrast.")
print()
print(f"{'FIELD':<22} {'LINES':>7} {'OCCURS':>7} {'WHOLEWORD':>10} {'FINDING':>8}"
      f"  LINE RULE MATCHES?")
print("-" * 78)

all_match = True
for field, expected in FIELDS.items():
    lines = count_lines(text, field)
    occurs = count_occurrences(text, field)
    words = count_whole_word(text, field)
    ok = lines == expected
    all_match &= ok
    print(f"{field:<22} {lines:>7} {occurs:>7} {words:>10} {expected:>8}"
          f"  {'yes' if ok else 'NO'}")

print()
if all_match:
    print("All four match under the matching-lines rule, as expected on the pin.")
else:
    print(
        "At least one field disagrees. On google-adk 2.6.1 that would mean the\n"
        "reconstruction is wrong; on any other version it means the adapter moved."
    )
print(
    "\nThe claim result 7 rests on is that encrypted_content — xAI's opaque\n"
    "reasoning field — appears zero times in THIS adapter, which holds under\n"
    "every rule. Elsewhere in google-adk 2.6.1 it is referenced; see the\n"
    "docstring."
)
