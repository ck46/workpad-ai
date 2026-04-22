# Workpad AI — Personal MVP Spec

> **Archived 2026-04-22.** Superseded by `docs/V1_SPEC.md` (consolidated v1). Kept for historical context — the library-first framing and normalized source/citation model here carried forward.

> Library-first engineering memory built on top of the current RFC wedge.

This document translates the broader personal-MVP idea into a repo-specific build plan.
It assumes the current RFC drafting and citation-verification stack stays in place and becomes
the substrate for a broader artifact library, retrieval layer, and memory workflow.

This is not a replacement for `docs/PRODUCT_VISION.md` or a retroactive rewrite of
`docs/V1_SPEC.md`. It is the next spec to build against from the current codebase.

## Why This Spec Exists

The current implementation already shipped most of the narrow RFC wedge:

- `apps/api/src/app/rfc_drafter.py` drafts RFCs from transcript + GitHub repo.
- `apps/api/src/app/citation_verifier.py` re-resolves repo citations and surfaces drift.
- `apps/api/src/app/core.py` persists conversations, artifacts, versions, RFC sources, citations, and repo cache.
- `apps/web/src/App.tsx` exposes a conversation-first UI with a `New RFC` modal and a durable workpad.

That wedge is useful, but it is still too close to "chat plus a generated document."

The personal-MVP goal is different:

- artifacts must accumulate into a real library,
- prior work must be easy to recover and reuse,
- manual writing must be first-class,
- retrieval must work across artifacts and linked source material,
- and drafting must become a capability of the memory system, not the whole product.

## Decisions Locked

These product and architecture decisions are now explicit.

### 1. The library is the primary navigation surface

The default home of the product should be the artifact library, not the conversation list.

Conversations remain useful, but only as orchestration:

- asking the AI to draft or revise,
- capturing the back-and-forth around an artifact,
- and preserving agent reasoning when needed.

They are no longer the main information architecture.

### 2. Artifacts are first-class outside conversations

An artifact must be openable, editable, searchable, and linkable without requiring the user to
remember which conversation created it.

Implementation note:

- in the short term, the database may still attach artifacts to a backing conversation for compatibility;
- in product behavior, artifacts are already first-class;
- in the longer-term schema, conversation provenance becomes optional metadata rather than the primary parent.

### 3. Retrieval operates on chunks, not just whole documents

Search and Q&A must work over chunked content:

- artifact sections,
- transcript segments,
- note excerpts,
- and selected source excerpts.

Whole-artifact embeddings alone are not enough for useful recall, comparison, or grounding.

### 4. The existing RFC wedge is substrate, not throwaway work

Do not replace or re-argue the current RFC stack.

Keep and reuse:

- `github_client.py`
- `rfc_drafter.py`
- `citation_verifier.py`
- citation rendering and preview UI
- repo cache
- artifact versioning

The new work should widen the product around these pieces.

## Product Definition

Workpad AI personal MVP is a single-user, local-first workspace for durable engineering artifacts.

An artifact can be:

- created manually,
- drafted from sources,
- linked to notes, transcripts, and repos,
- cited by other artifacts,
- reopened later with context,
- searched and queried alongside the rest of the library,
- and used as context for future drafts.

The core value is compounding memory, not one-shot generation.

## Product Scope

### In scope

- Single-user local app.
- Artifact library with recent/open/search/filter flows.
- Artifact types:
  - `rfc`
  - `adr`
  - `design_note`
  - `run_note`
- Manual artifact creation and editing without AI.
- Source attachment for:
  - repo
  - transcript
  - note
- Cross-artifact search and grounded Q&A.
- Drafting from current sources plus selected prior artifacts.
- Related artifact suggestions.
- Existing repo citation verification reused and generalized later.

### Explicitly out of scope

- Multi-user collaboration.
- Comments, mentions, permissions, billing.
- Slack/Teams/Figma/Linear integrations in the first personal MVP.
- Scheduled background jobs.
- Graph visualization UI.
- Reusable clause editing as a standalone subsystem.
- Full repo indexing for every attached repo revision.

### Important constraint

For the personal MVP, repo support should stay source-grounded but bounded.

Initial retrieval should index:

- artifacts,
- transcripts,
- notes,
- citation excerpts,
- and explicitly attached source excerpts.

It should not attempt to build a complete semantic index of every file in every attached repo.
Live repo reads can remain targeted and on-demand.

## Current Repo Baseline

The current codebase already gives us a useful foundation.

### Backend

`apps/api/src/app/core.py` currently defines:

- `Conversation`
- `Message`
- `Artifact`
- `ArtifactVersion`
- `SpecSource`
- `Citation`
- `RepoCache`

The current `Artifact` model already stores durable content and version history, but it is still
anchored to `conversation_id` and only exposes RFC typing through `spec_type`.

`apps/api/src/app/schemas.py` currently exposes:

- `SpecType = "rfc"` only
- citation kinds for repo and transcript references
- request/response models shaped around the current RFC flow

### Frontend

`apps/web/src/App.tsx` currently centers the UX on:

- a conversation sidebar,
- a chat workspace,
- and a `New RFC` modal.

That file already contains useful workpad, citation, and draft progress behavior, but the top-level
navigation is still thread-first rather than library-first.

## Primary UX Shape

The product should shift to the following top-level structure.

### Library-first shell

Primary left rail:

- Library
- Threads

Default landing view:

- recent artifacts,
- artifact type filters,
- search box / ask box,
- optional pinned tags or repos,
- "New artifact" action.

### Artifact page

When an artifact is open, the page should show:

- editor/preview surface,
- artifact summary and status,
- linked sources,
- related artifacts,
- freshness or drift state when relevant,
- quick actions to ask, compare, continue, or draft from it.

### New artifact flow

Replace `New RFC` with `New artifact`.

The flow should support:

1. Choose type: RFC, ADR, design note, run note.
2. Choose mode:
   - Start blank
   - Draft from sources
3. Attach optional sources:
   - repo
   - transcript
   - note
4. Select optional prior artifacts as context.
5. Save into the library immediately.

### Threads

Threads remain available as a secondary view:

- artifact-associated chat,
- general drafting help,
- source-grounding assistance,
- and execution context for AI actions.

They should not be the only way to rediscover work.

## Information Model

Do not model this as arrays hanging off `Artifact`.
Use normalized entities that can survive reuse and retrieval.

### Artifact

A durable work object.

Required fields:

- `id`
- `title`
- `artifact_type`: `rfc | adr | design_note | run_note`
- `content_markdown`
- `content_type`
- `summary`
- `status`: `draft | active | archived`
- `created_at`
- `updated_at`
- `last_opened_at`
- `origin_conversation_id` nullable

Notes:

- `content_type` stays because the editor stack already supports markdown and code.
- `artifact_type` replaces the narrow `spec_type`.
- `origin_conversation_id` is provenance, not the organizing parent.

### ArtifactVersion

Keep the existing version history model, but make its intent explicit:

- one row per saved artifact revision,
- `change_summary` describes what changed,
- version history remains artifact-scoped.

If the current `summary` field on `ArtifactVersion` remains in place for compatibility,
the application should treat it as a change summary rather than the artifact's abstract.

### Source

A reusable source record independent of one artifact.

Fields:

- `id`
- `kind`: `repo | transcript | note`
- `title`
- `provider`: e.g. `github`, later `local_git`
- `canonical_key`
- `provenance_json`
- `created_at`
- `updated_at`

Examples:

- repo source: repo slug, default branch, provider metadata
- transcript source: import method, transcript title, optional meeting metadata
- note source: local paste, note hash, optional user title

### SourceSnapshot

A pinned or captured version of a source.

Fields:

- `id`
- `source_id`
- `snapshot_ref`
- `content_text`
- `content_hash`
- `metadata_json`
- `created_at`

Examples:

- repo snapshot: commit SHA or selected excerpt set
- transcript snapshot: normalized transcript blob hash
- note snapshot: note hash

This table makes pinned references durable while still allowing the live source to evolve.

### ArtifactSourceLink

Join table between artifacts and sources.

Fields:

- `id`
- `artifact_id`
- `source_id`
- `snapshot_id`
- `role`: `primary | context | cited | derived_from`
- `added_by`: `user | ai | migration`
- `created_at`

This avoids storing source references as denormalized arrays on `Artifact`.

### Citation

The current citation row stays, but the personal MVP extends it.

Kinds for personal MVP:

- `repo_range`
- `repo_pr`
- `repo_commit`
- `transcript_range`
- `note_range`
- `artifact_ref`

Required additions:

- optional `source_snapshot_id`
- optional `excerpt_text_at_capture`

Why:

- `artifact_ref` is required early so artifacts can cite prior artifacts directly.
- capture excerpts improve retrieval, preview, and future re-grounding.

### ArtifactLink

Explicit relationships between artifacts.

Fields:

- `id`
- `from_artifact_id`
- `to_artifact_id`
- `kind`: `cites | derived_from | related | supersedes | pinned`
- `strength`
- `created_by`: `user | system | ai | migration`
- `created_at`

Important distinction:

- explicit links are stored here,
- inferred similarity is computed separately and can be cached,
- these are not the same thing.

### ArtifactTag

Simple tag join table.

Fields:

- `artifact_id`
- `tag`
- `created_at`

This is enough for the personal MVP. Do not build a full ontology.

### SearchChunk

The retrieval unit.

Fields:

- `id`
- `owner_kind`: `artifact | source_snapshot | citation_excerpt`
- `owner_id`
- `artifact_id` nullable
- `source_snapshot_id` nullable
- `chunk_type`
- `heading`
- `text`
- `ordinal`
- `token_count`
- `content_hash`
- `metadata_json`
- `created_at`

Initial chunk types:

- `artifact_section`
- `transcript_segment`
- `note_paragraph`
- `citation_excerpt`

### SearchEmbedding

Embeddings stored per chunk.

Fields:

- `chunk_id`
- `embedding_model`
- `vector_blob` or equivalent serialized representation
- `created_at`
- `updated_at`

SQLite note:

- use FTS5 for keyword search,
- store semantic vectors separately,
- do not over-design this into a separate service yet.

## Concrete Schema Changes From Current Code

These are the practical schema changes to make from the current models.

### `Artifact`

Keep:

- `id`
- `title`
- `content`
- `content_type`
- `version`
- timestamps

Add:

- `artifact_type VARCHAR(32) NULL`
- `status VARCHAR(16) NOT NULL DEFAULT 'draft'`
- `summary TEXT NOT NULL DEFAULT ''`
- `last_opened_at DATETIME NULL`
- `origin_conversation_id VARCHAR(36) NULL`

Transition rule:

- backfill `artifact_type = spec_type` where `spec_type` is set
- frontend reads `artifact_type ?? spec_type` during migration

### `Conversation`

Keep the table and existing APIs.

Product meaning changes:

- conversations become optional orchestration records
- artifact discovery should not depend on opening a conversation first

### `SpecSource`

Do not try to mutate `spec_sources` into the final generalized model in place.

Instead:

- keep `SpecSource` for the current RFC draft/verify path,
- add new generalized tables:
  - `sources`
  - `source_snapshots`
  - `artifact_source_links`

Reason:

- the current verifier depends on `spec_sources`,
- additive migration is safer than trying to repurpose an RFC-specific table midstream.

### `Citation`

Keep the current table.

Add columns:

- `source_snapshot_id VARCHAR(36) NULL`
- `excerpt_text_at_capture TEXT NULL`

Extend allowed kinds in application code:

- add `note_range`
- add `artifact_ref`

### New tables

Add:

- `artifact_links`
- `artifact_tags`
- `search_chunks`
- `search_embeddings`

Optional but recommended:

- `artifact_related_cache`

This cache can hold system-generated relatedness scores so the UI does not have to compute
semantic similarity on every page load.

## Retrieval Model

Retrieval is a core product feature, not a future add-on.

### What gets indexed first

Index the following:

- artifact titles
- artifact summaries
- artifact bodies chunked by headings / section boundaries
- transcript snapshots chunked by timestamp segment or paragraph group
- note snapshots chunked by paragraph
- citation excerpts
- tags

### What does not get fully indexed yet

Do not build a complete semantic index of every repo attachment in the personal MVP.

Instead:

- index repo excerpts that are actually cited or intentionally attached,
- keep live repo access for targeted reads,
- use artifact-linked repo metadata as a filter and retrieval hint.

### Search pipeline

Use a hybrid retrieval flow:

1. FTS keyword retrieval over titles, summaries, tags, and chunk text.
2. Semantic retrieval over `SearchChunk`.
3. Merge and dedupe candidate chunks.
4. Re-rank using:
   - artifact type
   - shared repo
   - recency
   - explicit links
   - user-selected scope
5. Build grounded answers with citations back to artifacts and source snapshots.

### Answer quality rule

Every library answer should cite:

- the artifact chunk it relied on,
- and the underlying source snapshot when available.

If only artifact-level support exists, the answer should still be returned, but that distinction
should be preserved in the response model for future UI treatment.

## AI Capabilities For The Personal MVP

### A. Draft artifact

Generalize the current RFC drafter to support:

- `rfc`
- `adr`
- `design_note`
- `run_note`

Inputs:

- selected sources
- selected prior artifacts
- chosen artifact template

Output:

- artifact draft
- citations
- summary
- explicit `ArtifactLink(kind='derived_from')` rows when prior artifacts were used

### B. Ask across library

New capability:

- ask over artifacts and linked source chunks
- return grounded answers with citations
- allow optional filters by artifact type, repo, tag, and artifact selection

### C. Continue artifact

Given an open artifact, the AI should help:

- extend a section
- rewrite for clarity
- ground a paragraph
- extract decisions
- compare against source-linked repo state

### D. Suggest related work

When viewing or drafting an artifact, show related artifacts ranked by:

1. explicit artifact links
2. shared source links
3. shared tags
4. semantic similarity

### E. Drift and verification

Keep the current RFC verification stack intact.

For the personal MVP:

- repo citation verification remains the first implemented freshness feature,
- drift stays on-demand initially,
- library-level freshness views come after retrieval and drafting over prior work.

## API Direction

Add a library API instead of forcing everything through conversation endpoints.

### Keep existing endpoints

- `/api/conversations/...`
- `/api/chat/...`
- `/api/specs/draft`
- `/api/artifacts/{id}/verify-citations`

These should continue to work during migration.

### Add library endpoints

Suggested initial surface:

- `GET /api/library/artifacts`
- `GET /api/library/artifacts/{artifact_id}`
- `POST /api/library/artifacts`
- `PUT /api/library/artifacts/{artifact_id}`
- `POST /api/library/artifacts/{artifact_id}/sources`
- `POST /api/library/search`
- `POST /api/library/ask`
- `GET /api/library/artifacts/{artifact_id}/related`

Compatibility note:

- `/api/specs/draft` can remain the RFC-specific wrapper during transition
- later, generalized drafting can move to `/api/library/artifacts/draft`

## Frontend Direction

The current `App.tsx` contains useful behavior but too much top-level responsibility.

Near-term UI work should favor:

- `LibrarySidebar`
- `ThreadSidebar`
- `ArtifactLibraryView`
- `ArtifactDetailView`
- `NewArtifactModal`
- `AskLibraryPanel`

This does not need to be a full frontend refactor before shipping, but the UX should move in
that direction as soon as the library becomes primary.

### Required behavior changes

- rename `New RFC` to `New artifact`
- add artifact type picker
- add a library list independent of conversations
- surface related artifacts and linked sources in the artifact view
- add search / ask entry point at the library level

## Migration Plan From The Current Codebase

This needs to be incremental and additive.

### Stage 0 — Preserve the existing RFC wedge

Do not break:

- RFC drafting
- citation rendering
- verify-citations endpoint
- exports
- current conversation flows

The current wedge is the safety net and the substrate.

### Stage 1 — Add library metadata without breaking compatibility

Backend:

- add `artifact_type`, `status`, `summary`, `last_opened_at`, `origin_conversation_id`
- add `sources`, `source_snapshots`, `artifact_source_links`
- add `artifact_tags`
- add library list/read/update endpoints

Data migration:

- backfill `artifact_type` from `spec_type`
- set `status = 'active'` for existing RFC artifacts
- initialize `summary` from title plus opening section or a simple summarizer
- set `origin_conversation_id = conversation_id`

UI:

- add Library tab or section
- allow opening artifacts directly from the library

Exit criterion:

- user can create, reopen, and browse artifacts from a library without caring which conversation created them

### Stage 2 — Introduce search chunks and library retrieval

Backend:

- add `search_chunks` and `search_embeddings`
- build chunkers for artifacts, transcripts, and notes
- implement keyword + semantic retrieval
- add `POST /api/library/search`
- add `POST /api/library/ask`

Data migration:

- backfill chunks for existing artifacts
- copy transcript and note text from `SpecSource` into generalized source tables and chunk them

UI:

- search box in library
- ask panel over the library
- result cards that jump to artifacts and source excerpts

Exit criterion:

- user can ask "What did I decide about auth?" and get a grounded answer from prior work

### Stage 3 — Generalize drafting on top of memory

Backend:

- generalize `rfc_drafter.py` into artifact drafting by type
- allow selected prior artifacts as drafting context
- create explicit `artifact_links` for derived drafts

UI:

- `New artifact` supports blank or AI-assisted creation
- prior artifact selection is part of the draft flow

Exit criterion:

- a new draft is materially better because it uses prior artifacts, not only fresh pasted context

### Stage 4 — Bring freshness back at the library level

Backend:

- extend verification to generalized artifact/source links
- compute per-artifact freshness summaries from citation states

UI:

- show freshness/drift indicators in the artifact detail view
- optionally surface stale artifacts in library filters

Exit criterion:

- users can see which artifacts may no longer match current repo state

## Backfill Strategy For Existing RFC Data

The current RFC data should seed the library instead of being stranded as legacy content.

### Existing artifacts

- preserve all existing `Artifact` rows
- map `spec_type='rfc'` to `artifact_type='rfc'`
- retain version history

### Existing RFC sources

For each `SpecSource` row:

- create or upsert a `Source`
- create a `SourceSnapshot`
- create an `ArtifactSourceLink`

Do not delete `spec_sources` yet.

### Existing citations

Keep current citations as-is.

Where possible:

- attach `source_snapshot_id`
- backfill `excerpt_text_at_capture` from the draft-time source data

### Existing conversations

Keep them all.

Use them as provenance and thread history, not as the only access path to artifacts.

## Build Order

This is the practical sequence to follow from here.

### Phase 1 — Library substrate

Ship:

- generalized artifact metadata
- library list view
- manual artifact creation
- generalized source tables

Do not ship:

- semantic retrieval yet
- generalized drafting yet

### Phase 2 — Retrieval and Q&A

Ship:

- chunk indexing
- keyword + semantic retrieval
- library ask mode
- related artifact suggestions

### Phase 3 — Drafting on top of memory

Ship:

- artifact-type templates
- selected prior artifacts as context
- generalized drafting flow

### Phase 4 — Verification and freshness

Ship:

- library-level drift surfacing
- broader source verification

This ordering keeps the new product honest:

- library before generation
- retrieval before polish
- memory before verification expansion

## Risks

### 1. The UI still feels chat-first

Mitigation:

- make the library the default landing surface as soon as library listing exists
- stop treating `New RFC` as the primary CTA

### 2. Retrieval underperforms because indexing is too coarse

Mitigation:

- ship chunked indexing early
- do not rely on whole-artifact embeddings

### 3. The generalized source model becomes overcomplicated

Mitigation:

- keep only `Source`, `SourceSnapshot`, and `ArtifactSourceLink`
- defer anything graph-like beyond explicit links and relatedness cache

### 4. Full repo indexing becomes a scope trap

Mitigation:

- keep repo retrieval targeted
- index cited/attached excerpts first
- treat full-repo semantic indexing as a later optimization, not a requirement

## Success Criteria

The personal MVP is successful when all of the following are true:

- artifacts are discoverable from a real library, not only through conversation history
- at least four artifact types are supported on one editor surface
- manual writing with source attachment is useful without invoking AI
- library search and Q&A recover prior reasoning from artifacts and linked sources
- new drafts improve because prior artifacts can be selected as context
- the existing repo citation and drift work still functions

The real usage test is straightforward:

- when starting technical thinking, it should feel more natural to open Workpad than to open a blank chat

## Non-goal Reminder

This spec is intentionally optimized for personal compounding value, not a marketable wedge for teams.

The question for this phase is not:

- "What is the smallest sellable product?"

The question is:

- "What is the smallest version that turns this repo's current RFC wedge into a durable engineering memory system?"
