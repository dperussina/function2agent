# 14 — Fixture Synthesis

## Table of contents

- [1. The decision register](#1-the-decision-register)
- [2. Tables that render](#2-tables-that-render)
- [3. Shapes that have produced false positives](#3-shapes-that-have-produced-false-positives)

## 1. The decision register

| # | Decision | Position |
|---|---|---|
| D-01 | **Invocation boundary** | Over the boundary. |
| D-02 | **Process** | Spec Kit drives. |
| D-03 | **Credentials** | BYO everything. |

## 2. Tables that render

| Configuration | Served operations |
|---|---|
| `api_server` | 22 |
| `enterprise` | 24 |
| `web` | 67 |

A pipe inside an inline code span is not a column separator, and neither is an
escaped one. An earlier ad-hoc validator in this repository reported a false
positive on exactly this row.

| Provider | Key shape |
|---|---|
| **xAI** | ACL strings — `api-key:endpoint:<chat\|image>`, wildcards. |
| **Anthropic** | Workload identity federation, `sub \| aud` claims. |

## 3. Shapes that have produced false positives

A citation identifier is not a rate: doi:10.1609/aaai.v40i40.40676, and
Preprints 202606.0238. A version is not a rate either: `specify-cli` 0.15.1,
constitution v1.1.0.

A vendor price is not our spend: $2.50/1k collections searches, and
$0.08 per session-hour, and $2.49/task.

A subset of a register is not a claim about its extent — D-02 through D-03 are
the ones that cost real money to be wrong about, and the register itself is
complete at D-03.

Proximity is not a pairing: route recall is **0.8961** (69 of 77) at precision
**1.0000**, and the tool arm sits at 27 of 41 measured tasks against a
pre-registered calibration band of 0.25–0.85.

An HTTP status pair is not a fraction: the probe answers 404/405 and the
discrimination is exact at 1.0000.

```text
This fenced block contains | pipes | and 0.1234 and D-99 and none of it counts.
| a | b |
```
