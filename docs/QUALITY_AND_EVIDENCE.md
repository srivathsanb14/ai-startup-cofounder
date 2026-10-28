# Quality and evidence

The goal of this project is *transparent* research: you should be able to see what is sourced, what is
guesswork, and how much to trust the whole report. This document describes each mechanism and its limits.

## 1. Evidence ledger (`evidence.py`)

Every search result or fetched page is registered with an id (`E1`, `E2`, ...). Duplicates (same URL) reuse the
same id. Agents see ids in tool observations and cite them in findings.

## 2. Grounding checks on findings

A finding the agent labels `fact` is kept as a fact only if it passes all of these, otherwise it becomes an
`estimate` with a recorded reason (shown in the report):

| Check | Fails when | Recorded reason |
|---|---|---|
| Citation exists | no cited id exists in the ledger | `no valid citation` |
| Numbers present | a number with 2+ digits in the claim (e.g. `12.5`, `2024`, `40`) is missing from the cited sources' text | `number(s) 99 not found in cited sources` |
| Wording overlap | fewer than 2 meaningful words (4+ letters, not stopwords) of the claim appear in the cited sources | `claim shares too little wording with its cited sources` |

Single-digit numbers are ignored ("3 competitors") because they match too easily and produce noise.

**What this catches:** fabricated statistics, citations pasted onto unrelated claims, uncited assertions.
**What it cannot catch:** a claim that reuses the right words and numbers but misreads the source, or a source that
is itself wrong. It improves honesty; it does not prove truth. Snippets are short, so a true claim from deeper in a
page can be downgraded; agents are told to `fetch_page` key pages to avoid this.

## 3. Competitor verification (`quality.verify_competitors`)

Each competitor name is normalized (suffixes like Inc/LLC removed) and searched for in the combined text of all
retrieved sources. The full name or its distinctive first word (4+ letters) counts as a match. The report shows
**seen in sources** or **NOT confirmed in sources**, and confirmed competitors rank first. A model naming a
competitor from memory is allowed, but it is visibly marked.

## 4. The review loop

### Automatic rules (`quality.rule_gaps`)
| Agent | Gap raised when |
|---|---|
| any | produced no output or failed |
| any | sources exist, the agent made tool calls, but none of its findings is a verified fact |
| Customer | no segments |
| Competitor | fewer than 3 competitors, or fewer than 2 of them appear in any evidence |
| Market | TAM, SAM or SOM missing/non-positive, or no method |
| Technical | no feasibility score |

### LLM critic
The Critic agent receives the research and the rule findings and adds only decision-relevant gaps. At most 3
gaps per round are acted on (one per agent, rules first). Each flagged agent is re-run with its previous answer
and the feedback, and the new output replaces the old one only if it is valid. The report's **Quality review**
section lists every redo and whether it improved.

## 5. Evidence grade (`quality.evidence_grade`)

```
score = 0.5 * (fact findings / all findings)
      + 0.2 * min(sources collected / 15, 1)
      + 0.2 * (top-3 competitors confirmed in evidence / 3)
      + 0.1 * (no agent failed)
A >= 0.70    B >= 0.50    C >= 0.30    D below
```

| Grade | Reading |
|---|---|
| A | strong sourcing; numbers are mostly traceable |
| B | good sourcing |
| C | thin sourcing; treat numbers as rough |
| D | mostly unsourced estimates (always the case offline or with the mock LLM) |

The grade is passed to the synthesizer so its language matches reality, and shown in the "At a glance" table.

## 6. Verdict guardrail (`quality.cap_verdict`)

The synthesizer may output `go`, `validate_first`, `pivot` or `no_go`. A `go` is **downgraded to
`validate_first`** unless **all** hold: evidence grade is A or B; LTV/CAC >= 3; operating break-even occurs
within 5 years. Invalid or missing verdicts become `validate_first`. The report prints the reason when a downgrade
happens. `pivot` and `no_go` are never upgraded.

## 7. Offline and mock modes

With `--offline` no evidence is retrieved, so no finding can be a fact; the report warns and grades D. With `--mock`
the report warns that its content is placeholder text.

## Tuning

- More thorough research: `MAX_TOOL_CALLS=8`, `CRITIC_ROUNDS=2` (slower, more model calls).
- Faster/cheaper drafts: `CRITIC_ROUNDS=0`, `MAX_EXTRA_SPECIALISTS=0`.
- Stricter or looser grounding: edit `STOPWORDS` and the overlap threshold in `evidence.grounding_problem`.
