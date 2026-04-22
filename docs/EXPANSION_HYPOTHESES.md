# Expansion Hypotheses

> Forward-looking notes on who Workpad AI could serve beyond the current core wedge.

This document captures possible customer and user expansions that are worth revisiting later. It is intentionally not a committed roadmap or source-of-truth product spec. Treat it as a strategy note: useful for future planning, messaging, and prioritization conversations.

For the current direction, see `docs/PRODUCT_VISION.md` and `docs/V1_SPEC.md`. The earlier personal-MVP and web-multiuser branches are archived under `docs/archive/`.

## Current Strongest Wedge

The strongest near-term user remains software-centric technical teams, especially:

- Staff and principal engineers writing RFCs and ADRs
- Platform and backend engineers making architecture decisions
- SRE and DevOps teams maintaining runbooks and incident knowledge
- AI / ML engineers working with prompts, evals, and changing system behavior

This matches the current product shape best: specs grounded in live technical sources, with citations and drift detection.

## Near-Term Expansion Candidates

These are the adjacent users most worth testing after the initial software-engineering wedge.

### 1. Platform / SRE / DevOps

Why they fit:

- They already rely on runbooks, postmortems, and operational decision records
- Their documentation drifts quickly as systems change
- The value of "live sources + verification" is immediately legible

Likely pad types:

- Runbooks
- Incident postmortems
- Operational ADRs
- Service onboarding docs

### 2. AI / ML Engineers

Why they fit:

- They work with fast-changing prompts, evaluations, traces, and experiments
- Their systems are harder to reason about from code alone
- They benefit from preserving why a prompt, model, or evaluation strategy was chosen

Likely pad types:

- Prompt specs
- Evaluation plans
- Experiment summaries
- Retrieval / agent design docs

### 3. Design + Engineering Pairs

Why they fit:

- Design handoff is already a "spec" problem in practice
- The work spans design files, tickets, code, and comments
- A living design/implementation doc could reduce repeated handoff friction

What would need to be true first:

- Strong Figma support
- Better cross-linking between design assets and code pads
- A clearer design-review workflow

### 4. PMs and EMs in Technical Workflows

Why they fit:

- They are often co-authors or primary consumers of PRDs, RFCs, and planning docs
- They care about alignment, reuse, and institutional memory

Why they are not the first wedge:

- The retention loop still depends on deep technical sources staying live
- Without repo- and system-level grounding, the product risks collapsing into generic docs software

## Longer-Term Expansion Candidates

These may be real markets, but they should be treated as separate product expansions, not simple user-additions.

### Hardware / Embedded / Systems Engineering

Why it is attractive:

- Requirements traceability is already a serious pain point
- Teams need durable links across requirements, designs, verification, and change history

Why it is materially different:

- Expectations around approvals, baselines, traceability, and compliance are much higher
- The source systems are different
- The buying motion is different from startup software teams

Conclusion:

This could become a real vertical later, but it should be treated as a distinct product branch rather than "software specs, but broader."

## Recommendation

Do not position the product as being for "all engineers" yet.

That is too broad for the current product shape and weakens the wedge. A better framing is:

> Living specs for technical teams shipping changing systems.

That keeps the product grounded in software-adjacent work today while leaving room to expand into other engineering domains later.

## Working Heuristic

The best future users are not defined mainly by job title. They are defined by workflow shape:

- They make consequential decisions
- Their reasoning lives across multiple source systems
- Their documentation drifts as reality changes
- They need those documents to stay trustworthy over time

If a segment matches that pattern, it is a plausible fit for Workpad AI.
