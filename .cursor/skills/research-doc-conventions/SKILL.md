---
name: research-doc-conventions
description: Applies the established house style for documents in this repository's research/ directory — dated header, TL;DR box, table of contents, inline source links, confidence annotations, an explicit unverified section, and a relevance-to-function2agent section. Use when writing a new research/NN-topic.md document, extending or editing an existing one, reviewing a research doc for consistency, or summarizing external findings that will be stored in research/.
---

# Research document conventions

The `research/` directory has an established house style. Match it. This skill describes it so new
documents do not drift.

**Do not edit existing research documents to conform.** Several may be actively in progress. Apply
this to documents you are authoring.

## Required skeleton

```markdown
# NN — Title: The Specific Claim or Question

**Last researched: YYYY-MM-DD**

---

## TL;DR — Key takeaways

> 1. **Bolded claim.** Supporting sentence with the load-bearing number and an inline link.
> 2. ...
> 8. **For `function2agent`:** what this means for the product.

---

## Table of contents

1. [Section name](#1-section-name)
...

---

## 1. First section
...

## N. Relevance to `function2agent`

## N+1. Open questions and things I could not verify

## N+2. Sources
```

Numbered filenames (`04-self-improving-agents.md`), numbered sections, and anchor-linked contents.
Cross-reference siblings as relative links: `[03](./03-graph-and-loop-architecture.md)`.

## The TL;DR box

Blockquoted numbered list, 6–8 items. Each item is a **claim, not a topic** — bolded lead clause,
then the evidence.

```
✅ 3. **The single most important empirical result in this space is negative:** LLMs asked
      to critique their own reasoning *without external feedback* get **worse**, and the
      apparent gains in early papers came from oracle labels deciding when to stop
      ([Huang et al., 2310.01798](https://arxiv.org/abs/2310.01798)).

❌ 3. This section covers self-correction and reflection loops.
```

The last item is conventionally **"For `function2agent`:"** — the product implication.

## Sourcing

- **Every non-obvious claim carries an inline link at the point of the claim**, not only in the
  Sources section. A reader should never have to scroll to check a number.
- Cite arXiv papers by ID and title: `([arXiv:2310.01798](https://arxiv.org/abs/2310.01798))`.
- Quote a primary source verbatim when the exact wording is load-bearing, in a blockquote.
- The **Sources section is grouped by section**, not one flat list, so a reader can go deeper on one
  topic.
- Prefer primary sources. Vendor engineering blogs count as primary for their own systems, and the
  doc should say when a source has a commercial interest in the conclusion.

## Confidence and negative findings

This is the part that distinguishes the house style from a summary. Three habits:

**1. Annotate confidence inline where a number is shaky.**

```
*Confidence: high on direction, medium on thresholds.* The 50k and 256k figures are useful
planning numbers, not physical constants; they will vary by model and task. Measure your own.
```

**2. State negative findings as findings, not caveats.** If the evidence says a popular technique
does not work, that is the headline, not a footnote. "The most consequential piece of hype-puncturing
in this document" is a sentence that belongs in these docs.

**3. Keep a "Claims I found poorly supported" subsection.** Name the popular claim in bold, then the
counter-evidence:

```
**"Multi-agent debate improves reasoning."** Found to be no better than self-consistency at
matched model-call counts ([2310.01798](...)). If you have 3× budget, spend it on
self-consistency or a verifier.
```

## The unverified section is mandatory

Every document ends with an honest list before Sources. Include:

- Claims sourced only to a preprint with no independent replication.
- Version numbers and tooling tables, flagged as fast-moving with the verification date.
- Engineering opinions held with strong priors but no controlled study — say so explicitly
  ("treat this as an engineering opinion, not a cited result").
- Documentation that contradicts itself, with instruction to verify against the installed version.
- Inferences the author made, labeled as inferences.

## Density

- Prose is dense; every paragraph carries a claim, a number, or a decision.
- **Tables for anything comparative.** Prefer a table over three paragraphs.
- Mermaid diagrams for topologies and decision procedures.
- Fenced code blocks for schemas, contracts, and decision ladders — including
  illustrative-but-not-runnable pseudocode, labeled as such.
- Good/bad example pairs where the difference is the point.
- No filler transitions, no restating the section heading, no "in this section we will."

Length is not the constraint; **density is the bar**. A 900-line document is fine if every section
earns its space. A 200-line document that summarizes without deciding does not.

## Voice

First person is used, and used for judgment specifically: *"I'd argue the whole system can be
organized around one claim"*, *"I would not build this in production."* Reserve it for taking a
position. Everything else is impersonal.

Say what you would do, not what one could do. These documents exist to settle decisions.

## Every document ends with product relevance

A `## Relevance to function2agent` section that converts the findings into concrete positions:
what the product should do, what it should refuse to do, and what falls out of the project's premise
for free. Numbered recommendations at the end of it.
