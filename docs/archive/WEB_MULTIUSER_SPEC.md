# Workpad AI — Web Multi-User Spec

> **Archived 2026-04-22.** Superseded by `docs/V1_SPEC.md` (consolidated v1). Kept for historical context — the multi-user framing carried forward, but the consolidated spec drops the workspace layer in favor of projects-as-top-level and scopes to 2–10 person teams.

> Workspace-first engineering memory for teams, built on top of the current RFC and citation substrate.

This document replaces the single-user personal-MVP direction as the current product target.
It preserves the useful parts of the current repo and reorients the product toward a hosted,
multi-user web application with accounts, workspaces, shared libraries, collaboration, and permissions.

This is not a replacement for:

- `docs/PRODUCT_VISION.md`, which remains the long-horizon narrative
- `docs/V1_SPEC.md`, which remains the original RFC wedge
- `docs/PERSONAL_MVP_SPEC.md`, which remains a valid historical branch of the product thinking

This is the current spec to build against.

## Why This Spec Exists

The repo already contains meaningful product substrate:

- `apps/api/src/app/rfc_drafter.py` drafts RFCs from transcript + GitHub repo
- `apps/api/src/app/citation_verifier.py` verifies repo citations and surfaces drift
- `apps/api/src/app/core.py` persists conversations, artifacts, versions, RFC sources, citations, and repo cache
- `apps/web/src/App.tsx` already supports a durable workpad, citations, preview popovers, and draft progress

But the current application is still shaped like a single-user prototype:

- no authentication
- no workspace model
- no sharing or permission boundaries
- no comments or mentions
- no notifications or inbox
- no clear separation between account state and product state
- conversation-first navigation instead of shared library-first navigation

If the product is meant to be a real web app for teams, these are not optional details.
They are part of the product definition.

## Product Definition

Workpad AI is a hosted, multi-user engineering memory workspace.

Teams use it to create, search, update, and discuss source-grounded artifacts such as:

- RFCs
- ADRs
- design notes
- run notes

Artifacts are durable objects in a shared workspace, not one-off chat outputs.

A workspace should let a team:

- draft artifacts from sources and prior work
- manually write and edit artifacts
- attach repos, transcripts, and notes
- cite underlying sources and other artifacts
- search across the shared library
- ask questions over prior decisions and current sources
- comment and collaborate on artifacts
- see activity and notifications
- return later and recover both decisions and rationale

The product is not “AI-generated docs.”
The product is a shared engineering memory system with AI built into the workflow.

## Core Shift From The Personal Spec

The single-user spec optimized for personal compounding value.
This spec optimizes for collaborative compounding value.

The key changes are:

- account and session management are mandatory
- workspaces replace the single-user library as the top-level container
- artifacts belong to a workspace
- permissions and visibility become first-class
- collaboration surfaces are part of the normal artifact experience
- notifications and activity matter because work is shared

The product still stays library-first.
The center of gravity is a shared artifact library, not a chat log.

## Product Principles

### 1. The workspace library is the product

The default experience should be the shared artifact library, not the thread list.

Threads still matter, but they are secondary.
They orchestrate drafting and discussion; they are not the main information architecture.

### 2. Artifacts are first-class shared objects

An artifact must be discoverable, permissioned, linkable, commentable, and reusable without depending
on a specific conversation to find it again.

### 3. AI must live inside shared memory

Drafting, answering questions, and comparing work should all pull from:

- current sources
- prior artifacts
- workspace context
- permissions-aware retrieval

### 4. Collaboration must feel native

Comments, mentions, ownership, status, and activity should feel built into the artifact lifecycle,
not bolted on as generic social features.

### 5. The current RFC/citation substrate is still useful

Do not throw away:

- citation rendering and preview UI
- citation verification/drift logic
- repo caching
- artifact versioning
- repo + transcript drafting logic

Those become shared workspace capabilities.

## Product Scope

### In scope

- Hosted web app
- Accounts and sessions
- Multi-user workspaces
- Workspace membership and invites
- Roles and permissions
- Shared artifact library
- Artifact types:
  - `rfc`
  - `adr`
  - `design_note`
  - `run_note`
- Manual editing and AI-assisted drafting
- Source attachment for:
  - repo
  - transcript
  - note
- Cross-artifact search and grounded Q&A
- Comments and mentions
- Activity history and notifications/inbox
- Related artifact suggestions
- Existing repo citation verification reused and later generalized

### Explicitly out of scope for the first web multi-user version

- Billing and payment collection
- Enterprise SSO / SCIM
- Fine-grained legal/compliance controls
- Full external publishing/export system
- Slack/Teams/Figma/Linear integrations in the first shared-workspace release
- Graph visualization UI
- Rich workflow automation
- Scheduled background verification jobs across every workspace by default

### Important constraint

Do not let “multi-user” turn into “enterprise platform” too early.

The first web multi-user version should feel like:

- a serious collaborative engineering tool
- not a generic B2B admin console
- not a project management clone
- not a full enterprise knowledge suite

## Primary User And Team

### Primary customer

Engineering teams of roughly 5–80 people.

### Core users inside the workspace

- staff/principal engineers drafting RFCs and ADRs
- engineering managers preserving decision history
- senior ICs and tech leads continuing prior design work
- new hires recovering context and rationale

### Non-target for this phase

- anonymous public collaboration
- enterprise-wide rollouts with custom governance
- generic documentation teams
- consumer note-taking use cases

## User Jobs

The product is successful when a team uses it for these recurring jobs:

1. Draft a new RFC/ADR/design note from repo context and notes.
2. Recover a prior decision and the rationale behind it.
3. Continue prior technical thinking without reconstructing context manually.
4. Reuse prior reasoning, source links, and artifact structure in new work.
5. Collaborate on an artifact with comments, mentions, and shared visibility.
6. Ask a workspace-level question like “What did we decide about auth?” and get a grounded answer.

## Top-Level Product Shape

The authenticated app should feel like:

- Workspace home
- Library
- Threads
- Ask / Search
- Inbox
- Settings

### Workspace home

The workspace home is not just a dashboard.
It should be a useful command surface with:

- recent artifacts
- drafts needing attention
- assigned mentions/comments
- recent activity
- suggested related work
- quick actions to create a new artifact or ask the workspace

### Library

The shared library is the core durable surface.

Minimum capabilities:

- list artifacts
- filter by type
- filter by status
- filter by owner / contributor / repo / tag
- open recent artifacts
- search by title, content, summary, comments, tags, and source text
- show linked sources
- show related artifacts
- show ownership and visibility

### Threads

Threads remain useful for:

- artifact-associated AI drafting
- open-ended technical exploration
- follow-up discussion around existing work
- orchestration before something becomes a durable artifact

Threads are secondary and workspace-aware.

### Ask / Search

This is a first-class product surface, not a small search box.

Users should be able to:

- search keywords
- ask questions over the workspace library
- filter scope by artifact type, repo, team area, and visibility
- jump into artifacts and cited sources from answers

### Inbox

Inbox / notifications should cover:

- mentions
- comments on followed artifacts
- invite acceptance or membership changes
- artifact status changes
- AI-generated suggestions later, if useful

### Settings

Separate clearly:

- account settings
- workspace settings

## Required Product Areas

### Public product area

- landing page
- sign in
- sign up
- forgot password
- reset password
- invite acceptance

### Authenticated product area

- workspace onboarding
- workspace switcher
- workspace home
- shared library
- artifact detail/editor
- new artifact flow
- AI drafting flow
- ask/search surface
- comments/discussion
- inbox/notifications
- account settings
- workspace settings
- member management
- invite flow

## Authentication And Identity

Authentication is mandatory in this version.

### Required auth capabilities

- account creation
- sign in
- sign out
- password reset
- email verification later if needed
- persistent session handling
- invite acceptance flow
- account profile/settings

### Recommended identity model

- `User`
- `Session`
- `Workspace`
- `WorkspaceMember`
- `Invite`

### Session-aware UX requirements

- signed-out and signed-in shells must be distinct
- routes must respect auth state
- workspace context must be visible once signed in
- account state and workspace state must be clearly separated

## Workspace Model

The workspace is the top-level collaboration boundary.

### Workspace responsibilities

- owns artifacts
- owns shared threads
- owns members, roles, and invites
- owns shared search scope
- owns notifications/activity relevant to that team

### Roles

The first version should support a small role model:

- `owner`
- `admin`
- `member`
- `viewer`

Keep role semantics simple and understandable.

### Permission areas

At minimum:

- view artifact
- comment on artifact
- create artifact
- edit artifact
- invite members
- manage workspace settings

## Artifact Model

Artifacts remain the core durable object.

### Artifact types

- `rfc`
- `adr`
- `design_note`
- `run_note`

### Artifact fields

- `id`
- `workspace_id`
- `title`
- `artifact_type`
- `content_markdown`
- `content_type`
- `summary`
- `status`: `draft | active | archived`
- `visibility`: `workspace | restricted`
- `owner_user_id`
- `created_by_user_id`
- `created_at`
- `updated_at`
- `last_opened_at`

### Collaboration-related artifact metadata

- list of contributors
- watchers/followers later if needed
- comment count
- mention count
- recent activity summary

### Artifact experience requirements

When viewing an artifact, the user should see:

- content/editor
- summary
- type
- status
- linked sources
- citations
- related artifacts
- comments/discussion
- recent activity
- ownership/contributor context
- quick AI actions

## Source Model

The source model should remain normalized and reusable.

### Source

Kinds:

- `repo`
- `transcript`
- `note`

Fields:

- `id`
- `workspace_id`
- `kind`
- `title`
- `provider`
- `canonical_key`
- `provenance_json`
- `created_at`
- `updated_at`

### SourceSnapshot

Pinned or captured source state.

Fields:

- `id`
- `source_id`
- `snapshot_ref`
- `content_text`
- `content_hash`
- `metadata_json`
- `created_at`

### ArtifactSourceLink

Join table between artifacts and sources.

Fields:

- `id`
- `artifact_id`
- `source_id`
- `source_snapshot_id`
- `role`: `primary | context | cited | derived_from`
- `added_by_user_id` nullable
- `added_by_system`
- `created_at`

## Citation Model

Keep the current citation subsystem and extend it for workspace use.

Initial citation kinds:

- `repo_range`
- `repo_pr`
- `repo_commit`
- `transcript_range`
- `note_range`
- `artifact_ref`

Recommended fields:

- `id`
- `artifact_id`
- `source_snapshot_id` nullable
- `anchor`
- `kind`
- `target_json`
- `excerpt_text_at_capture`
- `resolved_state`
- `last_checked_at`
- `last_observed_json`

### Why `artifact_ref` matters early

In the team version, artifact-to-artifact references are not optional.
They are part of the collaborative memory graph.

## Collaboration Model

### Comments

Comments must be first-class.

Required comment features:

- artifact-level comments
- inline or anchored comments later if needed
- mentions
- timestamps
- author identity
- edited/deleted state

### Activity

Activity should cover:

- artifact created
- artifact updated
- comment added
- member invited
- status changed
- source attached
- draft generated by AI

### Notifications / Inbox

Notifications should be generated for:

- direct mentions
- comments on artifacts the user owns or follows
- invite/membership actions
- assigned or requested review states later if added

Keep notifications actionable and tied to real objects.

## Retrieval Model

Retrieval remains central.
Now it must be workspace-aware and permission-aware.

### What gets indexed first

- artifact titles
- artifact summaries
- artifact body chunks
- transcript snapshot chunks
- note snapshot chunks
- citation excerpts
- comments
- tags

### Repo indexing constraint

Do not fully index every repo attachment by default in the first multi-user version.

Instead:

- index cited or intentionally attached excerpts
- use repo metadata as a retrieval filter
- keep live repo reads targeted

### Search pipeline

1. Keyword retrieval over titles, summaries, tags, comments, and chunk text
2. Semantic retrieval over chunked content
3. Permission filtering by workspace membership and visibility
4. Re-ranking using:
   - artifact type
   - shared repo
   - recency
   - explicit artifact links
   - comment/activity signals
   - user-selected filters
5. Grounded answer generation with citations

### Answer quality rule

Workspace answers should cite:

- the artifact chunk used
- the underlying source snapshot when available
- and ideally the linked artifact when the answer depends on a prior artifact decision

## AI Capability Set

### A. Draft artifact

Draft from:

- current sources
- selected prior artifacts
- workspace context
- artifact templates

Supported artifact types:

- `rfc`
- `adr`
- `design_note`
- `run_note`

### B. Ask over workspace

Answer questions across:

- artifacts
- comments
- source snapshots
- related citations

Answers must respect permissions and visibility.

### C. Continue artifact

Given an existing artifact, AI should help:

- expand sections
- revise wording
- ground claims
- compare against repo state
- extract decisions
- prepare review-ready summaries

### D. Suggest related work

When viewing or drafting an artifact, suggest related workspace artifacts based on:

- explicit links
- shared sources
- semantic similarity
- shared tags
- shared repo context

### E. Verification and drift

Keep the current repo citation verification stack.

Later, elevate it into a workspace capability:

- artifact freshness indicators
- stale citation surfacing
- eventually inbox-worthy drift summaries if warranted

## Information Model

This should be normalized, not array-based.

### Core entities

- `User`
- `Session`
- `Workspace`
- `WorkspaceMember`
- `Invite`
- `Artifact`
- `ArtifactVersion`
- `Thread`
- `Message`
- `Source`
- `SourceSnapshot`
- `ArtifactSourceLink`
- `Citation`
- `ArtifactLink`
- `Comment`
- `Notification`
- `SearchChunk`
- `SearchEmbedding`

### ArtifactLink

Explicit relationships between artifacts.

Fields:

- `id`
- `workspace_id`
- `from_artifact_id`
- `to_artifact_id`
- `kind`: `cites | derived_from | related | supersedes | pinned`
- `strength`
- `created_by_user_id` nullable
- `created_by_system`
- `created_at`

### SearchChunk

The retrieval unit.

Chunk types:

- `artifact_section`
- `transcript_segment`
- `note_paragraph`
- `citation_excerpt`
- `comment`

### SearchEmbedding

Store semantic vectors by chunk.

Use:

- keyword search plus semantic retrieval
- not semantic-only search

## Current Repo Baseline And Migration Reality

The current codebase is still single-user and conversation-first.

### Backend reality today

`apps/api/src/app/core.py` currently centers around:

- `Conversation`
- `Message`
- `Artifact`
- `ArtifactVersion`
- `SpecSource`
- `Citation`
- `RepoCache`

This is still useful, but it lacks:

- `User`
- `Workspace`
- membership
- invites
- comments
- notifications
- workspace-aware permissions

### Frontend reality today

`apps/web/src/App.tsx` still centers the UX on:

- conversation sidebar
- chat-first shell
- `New RFC` modal

This needs to become a real authenticated app shell.

## Concrete Schema Direction From The Current Codebase

### Keep and evolve

Keep:

- `Artifact`
- `ArtifactVersion`
- `Citation`
- repo cache
- existing drafting and verification logic

### Add mandatory web entities

Add:

- `users`
- `sessions`
- `workspaces`
- `workspace_members`
- `invites`
- `comments`
- `notifications`

### Update `Artifact`

Move from conversation-owned to workspace-owned.

Recommended additive fields:

- `workspace_id`
- `owner_user_id`
- `created_by_user_id`
- `visibility`
- `artifact_type`
- `status`
- `summary`
- `last_opened_at`

Compatibility note:

- `conversation_id` can remain temporarily during migration
- artifacts should become openable from the library without opening a conversation first

### Update `Conversation`

Conversations/threads become workspace-scoped.

Recommended fields:

- `workspace_id`
- `created_by_user_id`
- `visibility`
- `artifact_id` nullable when the thread is tied to an artifact

### Keep `SpecSource` only as a transitional table

As in the personal spec, do not twist `spec_sources` into the final generalized model in place.

Instead:

- preserve it for the current RFC flow
- add generalized source tables
- migrate forward additively

## Permission Model

Keep this simple in the first version.

### Workspace-level permissions

- owners/admins manage members and settings
- members create and edit artifacts and comments
- viewers can read and comment only if allowed

### Artifact visibility

Start with:

- `workspace`
- `restricted`

Do not overbuild per-user ACLs unless needed.
`restricted` can be implemented as explicit allow-lists later if necessary.

## UI Direction

The frontend should become an authenticated app shell with clear workspace structure.

### Public routes

- landing
- sign in
- sign up
- forgot password
- reset password
- invite acceptance

### Authenticated routes

- workspace home
- library
- artifact detail
- threads
- ask/search
- inbox
- members/invites
- account settings
- workspace settings

### Required shell elements

- workspace switcher
- user/account menu
- primary nav
- “New artifact” primary CTA
- global ask/search entry point
- inbox/notification indicator

## Build Order

The order matters.
Do not jump straight to collaborative polish before auth and workspace substrate exist.

### Phase 1 — Auth and workspace substrate

Ship:

- account model
- sessions
- workspace model
- invites
- membership/roles
- authenticated app shell

Exit criterion:

- users can sign in, join or create a workspace, and see a workspace-scoped app shell

### Phase 2 — Shared library and artifact ownership

Ship:

- workspace-scoped artifacts
- library-first navigation
- artifact ownership and visibility
- manual artifact creation and editing

Exit criterion:

- artifacts are clearly shared workspace objects, not hidden behind conversations

### Phase 3 — Retrieval and ask

Ship:

- chunk indexing
- search
- workspace ask mode
- related artifact suggestions

Exit criterion:

- a user can recover prior workspace decisions without manually hunting through threads

### Phase 4 — AI drafting over shared memory

Ship:

- generalized drafting across artifact types
- use of selected prior artifacts as context
- explicit artifact links for derived drafts

Exit criterion:

- new artifacts are materially better because they build on shared prior work

### Phase 5 — Comments, activity, and inbox

Ship:

- comments
- mentions
- activity timeline
- inbox/notifications

Exit criterion:

- collaboration feels native to the artifact experience

### Phase 6 — Verification and drift

Ship:

- workspace-visible freshness indicators
- drift surfacing in library and artifact views

Exit criterion:

- teams can see which shared artifacts may no longer match current code

## Risks

### 1. It becomes a generic SaaS shell

Mitigation:

- keep the artifact library and engineering-memory behavior central
- do not let settings/membership UI dominate the product

### 2. Multi-user scope overwhelms the core memory loop

Mitigation:

- build auth/workspace first, but keep the next major focus on library and retrieval

### 3. Permissions complicate retrieval too early

Mitigation:

- keep the initial visibility model simple
- make retrieval workspace-aware, but do not start with fine-grained ACL complexity

### 4. Comments and notifications become noisy

Mitigation:

- tie them tightly to artifacts and mentions
- avoid generic social feed behavior

### 5. The current repo remains shaped like a prototype for too long

Mitigation:

- prioritize the authenticated shell and workspace model early
- stop adding major product features on top of the old chat-first IA

## Success Criteria

The first successful web multi-user version is done when:

- users can sign up, sign in, and join or create a workspace
- artifacts are shared workspace objects with clear ownership and visibility
- the library is the primary navigation surface
- teams can search and ask across the shared library
- comments and mentions work inside the artifact experience
- new artifacts can be drafted from current sources plus prior workspace artifacts
- the app feels like a coherent web product, not a single-user localhost prototype

The strongest behavioral test is:

- when a team needs to recover or continue technical reasoning, opening Workpad feels more natural than starting another isolated doc or chat

## Non-goal Reminder

This spec is not trying to become:

- a project management suite
- a generic internal wiki
- a full enterprise knowledge governance platform

It is trying to become:

- a shared engineering memory workspace with AI, grounding, retrieval, and collaboration built in

## Summary

Workpad AI web multi-user spec is:

- a hosted collaborative web app
- centered on shared artifact libraries
- grounded in live sources
- powered by workspace-aware retrieval and AI
- equipped with auth, workspaces, comments, notifications, and permissions
- and built incrementally on top of the repo’s existing RFC/citation substrate

The product is no longer just “a better drafting tool for one person.”
It is a collaborative engineering memory system for teams.
