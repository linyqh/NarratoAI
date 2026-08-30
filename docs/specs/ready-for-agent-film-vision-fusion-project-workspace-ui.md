---
title: Film Vision Fusion project-centered workspace UI
status: ready-for-agent
tracker: local
labels:
  - ready-for-agent
  - film-vision-fusion
  - ui-remediation
---

## Problem Statement

Film Vision Fusion currently appears as conditional controls inside the legacy generation form. Its project state, long-running tasks, approvals, versions, evidence review, failure recovery, and render readiness are spread across transient session surfaces. A creator can select the new mode and still see the old three-column settings page; the intended Project Library, project creation flow, and persistent workspace are not the primary application experience.

This makes expensive work difficult to understand and recover. Refreshing or leaving the page can obscure ownership, users cannot reliably see which project or artifact a task belongs to, and technically valid scripts can move through fragmented review steps without one coherent view of narration, picture, evidence, conflicts, and Render Preflight. The existing conditional Fusion Workspace is therefore an implementation foundation, not completion of the planned Phase 3 UI.

## Solution

Replace the legacy Film Vision Fusion entry with a visible, persistent, project-centered creator experience. The application opens on a Project Library, creates a durable Fusion Project before expensive work begins, and performs setup, evidence preparation, narration, matching, review, and rendering inside that project's Fusion Project Workspace.

The experience uses a dark desktop-first shell, an explicit New Fusion Project flow, six freely inspectable but safely gated Fusion Workflow Stages, a global Task Center, synchronized evidence review, durable drafts and versions, and Render Preflight as the sole render authority. Existing reliability, Narrative Map, Fusion Matching Task, review-decision, version, Evidence Conflict, and preflight behavior are reused through stable application services rather than reimplemented in UI components.

## User Stories

1. As a creator, I want the application to open on a Project Library, so that Film Vision Fusion work is organized by durable projects rather than browser sessions.
2. As a creator, I want to search, filter, sort, and switch the presentation of projects, so that I can quickly find active and completed work.
3. As a creator, I want project cards to show status, stage, activity, progress, and review count, so that I understand each project's condition without opening it.
4. As a creator, I want to create a durable draft project before uploading or analyzing media, so that navigation cannot discard my configuration.
5. As a creator, I want a two-column setup page with configuration beside source import, so that the initial workflow remains focused and understandable.
6. As a creator, I want to reference local source movies without copying them, so that multi-gigabyte files do not consume duplicate storage.
7. As a creator, I want browser uploads copied into project-managed storage, so that their lifecycle and deletion behavior are explicit.
8. As a creator, I want one project to support an ordered Source Video Sequence, so that multi-part or multi-source commentary remains coherent.
9. As a creator, I want each source to show identity, availability, duration, subtitle state, and Visual Evidence state, so that incompatible inputs are visible before generation.
10. As a creator, I want moved or changed local files reported as offline or identity-changed, so that stale evidence is never silently reused.
11. As a creator, I want setup, evidence, narration, matching, review, and output stages visible at all times, so that I understand the whole production journey.
12. As a creator, I want to inspect any stage while unsafe actions remain gated, so that investigation does not require weakening prerequisites.
13. As a creator, I want every blocked action to explain its missing prerequisite, so that disabled controls are never mysterious.
14. As a creator, I want visual-analysis estimates before starting, so that I understand the expected duration and request volume.
15. As a creator, I want visual analysis to continue when I leave its page, so that long-running work is not owned by the browser view.
16. As a creator, I want tasks to recover after application restart, so that interrupted work is not falsely shown as running or silently lost.
17. As a creator, I want narration streaming to show waiting, active, idle, timeout, complete, failed, and cancelled states, so that long model requests remain understandable.
18. As a creator, I want narration and Narrative Map edits saved as Content Drafts, so that editing does not immediately invalidate approved work.
19. As a creator, I want an impact preview before applying a draft, so that I can see which matches, reviews, and renders will become stale.
20. As a creator, I want to review, edit, approve, or explicitly skip a Narrative Map checkpoint, so that story interpretation remains under my control.
21. As a creator, I want the Fusion Segment Plan presented before matching, so that I can review narrative coverage and source windows before more model calls.
22. As a creator, I want an invalid planning response preserved and recoverable, so that a long-running LLM response does not end as a generic error.
23. As a creator, I want each Segment Match to show source, Core Window, attempt, status, and recovery action, so that failures are localized.
24. As a creator, I want only the affected segment retried, so that completed work and provider cost are preserved.
25. As a creator, I want stale task results kept for inspection but prevented from replacing current work, so that concurrent edits cannot corrupt project state.
26. As a creator, I want review blockers ordered before optional quality suggestions, so that I resolve safety issues first.
27. As a creator, I want selecting a review item to synchronize video, timeline, narration, Story Beat, subtitles, and both evidence types, so that I can judge it in context.
28. As a creator, I want unsafe-to-locate findings labeled explicitly, so that the UI never jumps to an unrelated source or timestamp.
29. As a creator, I want acknowledge, adopt, ignore, override, and undo decisions saved immediately, so that refresh does not erase review work.
30. As a creator, I want content mutations to create versions, so that I can compare and restore prior approved states.
31. As a creator, I want version comparison to show changed beats, ranges, conflicts, Original Sound Ratio, quality findings, and preflight state, so that I understand the consequence of a change.
32. As a creator, I want Render Preflight to separate blockers, warnings, and passed checks, so that render availability has one clear authority.
33. As a creator, I want warning overrides to require a saved reason, so that later review can distinguish a conscious trade-off from an omission.
34. As a creator, I want each successful render stored as an immutable Render Outcome, so that exporting again never overwrites provenance.
35. As a creator, I want a global Task Center with continue, cancel, retry, and diagnostics actions, so that work across projects remains observable.
36. As a creator, I want normal screens to use operational language instead of task IDs, raw JSON, or stack traces, so that errors remain actionable.
37. As an advanced creator, I want bounded diagnostics available separately, so that troubleshooting is possible without exposing credentials or hidden model reasoning.
38. As a creator, I want archived and trashed projects recoverable, so that routine cleanup is reversible.
39. As a creator, I want permanent deletion to list exactly what will be removed, so that referenced local movies and managed project data cannot be confused.
40. As a creator, I want legacy work imported only after I select related sources and artifacts, so that unrelated historical records are never grouped automatically.
41. As a creator, I want the old Film Vision Fusion selector to redirect into the new project flow, so that there is one production experience rather than two competing interfaces.
42. As a mobile user, I want to monitor and acknowledge work, so that lightweight task supervision remains possible away from desktop.
43. As a desktop creator, I want the three-region review workspace optimized for wide screens, so that video, queue, and evidence remain visible together.
44. As a maintainer, I want project status and stage readiness derived once, so that separate pages cannot disagree about what is safe.
45. As a maintainer, I want UI actions expressed as application commands and projections, so that Streamlit components do not own persistence or workflow policy.
46. As a maintainer, I want task completion checked against its input fingerprint, so that old-version work cannot become authoritative.
47. As a maintainer, I want deterministic fixtures and recorded real-media acceptance, so that UI correctness and final viewing quality are both verifiable.
48. As a maintainer, I want the legacy Fusion UI removed only after parity and acceptance, so that migration does not strand existing workflows.

## Implementation Decisions

- A Fusion Project is the ownership boundary for source references, managed assets, settings, artifacts, background tasks, drafts, versions, review decisions, and Render Outcomes.
- Project creation occurs before expensive work and persists atomically. Browser session state may cache selections but is never the project authority.
- The application uses a dedicated multipage Streamlit experience rather than introducing a separate frontend and local API layer during this phase.
- The Project Library is the default Film Vision Fusion entry. Traditional Compatibility Mode remains a deliberate, separately labelled entry while project parity is completed; selecting it must open the existing Film Vision Fusion controls rather than silently redirecting.
- Local Source Videos remain external references with verified identity. Managed Project Assets belong to the project lifecycle. Permanent deletion never removes referenced local movies.
- The Source Video Sequence defines creator-controlled ordering and keeps all evidence and timestamps scoped to a stable source identity.
- The workspace contains six Fusion Workflow Stages: Setup, Media & Evidence, Narration & Narrative Map, Picture Matching, Review, and Output.
- Stages are freely navigable for inspection. Durable Review Checkpoints and prerequisites gate mutating or expensive actions, not page access.
- Project status is derived in one projection policy with a single precedence order. Selected page and transient widget state do not determine status.
- UI pages consume stable project commands and projections. They do not write project records directly, reinterpret renderability, mutate task status, or decide invalidation.
- Project writes are atomic and versioned by schema. Large artifacts are referenced rather than embedded in the project record.
- Every mutating background task captures its project, source where applicable, input version, and input fingerprint. A mismatched completion becomes a Stale Task Result.
- Different-source analysis may run concurrently. Content-mutating narration, matching, finalization, and repair work is serialized per project where concurrent completion could compete for authority.
- Ordinary configuration autosaves. Narration, Narrative Map, and Fusion Script edits remain Content Drafts until the creator accepts an impact preview.
- Applying a Content Draft creates a new version and invalidates only dependent work. Existing unrelated evidence and immutable Render Outcomes remain available.
- Review selection synchronizes source identity, time range, Segment Match, Story Beat, narration, Subtitle Evidence, and Visual Evidence. Missing mappings never fall back to approximate unrelated content.
- Review decisions persist immediately with undo. Content mutations remain draft-based and versioned.
- Render Preflight is the sole render decision seam. Render Outcomes bind one active version, one output-settings snapshot, and one preflight record.
- The global Task Center owns cross-project monitoring; project pages show a focused summary of the current project's work.
- Creator-facing errors follow one operational contract: what happened, what was preserved, what is blocked, recommended next action, and available actions.
- Raw provider metadata and bounded output excerpts belong in advanced diagnostics. Credentials, full prompts, hidden model reasoning, and Python stack traces are excluded.
- The P0 Script Planning Reliability Gate must pass before project UI slices can be declared releasable.
- Delivery is ordered: legacy-boundary freeze, project repository and projections, library/setup, evidence/tasks, narration/matching, review, output/migration, then visual and real-media acceptance.

## P0: Project setup parity and traditional compatibility

The first remediation priority is capability parity at project creation. A creator must not need to abandon Project Workspace Mode merely to access a traditional Film Vision Fusion input, and must be able to deliberately use the traditional workflow when its session-based behavior is preferred.

1. **Two explicit modes.** Project Workspace Mode is the recommended durable workflow. Traditional Compatibility Mode remains a separately labelled entry for Film Vision Fusion. It never downgrades a project or live-synchronizes with it.
2. **Explicit transfers only.** Project-to-traditional transfer copies non-secret settings and usable source references once. Traditional-to-project transfer is a separately confirmed import that binds chosen assets to the new project. Neither transfer grants project render authority to unvalidated legacy artifacts.
3. **Style parity.** Project setup exposes the same supported commentary-style vocabulary used by Fusion generation, including an existing saved value. The chosen value is persisted as a project setting and is passed to narration and matching unchanged.
4. **Executable subtitle strategy.** Setup presents human-readable choices: `优先使用现有字幕，缺失时自动转录`, `仅使用我提供的字幕`, and `始终重新转录`. Every source independently shows its adopted subtitle, source, status, and available actions: select/upload, transcribe, translate, calibrate, and preview. A strategy cannot claim readiness until it has produced source-bound subtitle evidence.
5. **TTS configuration snapshot.** Project setup reuses the traditional engine and voice selection behavior. It persists an engine, voice name, and non-secret voice parameters as a Provider Configuration Snapshot. Provider credentials and machine endpoints remain in local configuration; unavailable selected providers block output with a clear recovery action rather than falling back silently.
6. **Local resource parity.** Setup can select videos from the existing resource-video directory as Local Source Video references. It also accepts a manually entered local path. Neither choice copies or deletes the original movie.
7. **Managed-upload explanation.** Browser upload is labelled `上传并由项目托管` and explains that it copies a source into project storage for portability and deletion with the project. It is distinct from a local reference, which is not copied and may become offline if moved.
8. **Visual-artifact parity.** Each source may list local Visual Evidence Artifact JSON files or upload one. Import validates the selected source's content identity. An unverified legacy artifact may be marked regression-only for inspection, but cannot enable formal narration, matching, or rendering.
9. **Source affinity.** Subtitle derivatives and visual artifacts are always Source-bound Evidence Artifacts. A multi-source project never applies one source's evidence to another source implicitly.

P0 acceptance requires project setup to expose all eight creation inputs above, preserve selections across refresh, pass the resulting subtitle and TTS snapshots into the existing pipeline, and prove via automated tests that mode entry, source identity checks, and cross-source rejection are safe.

## Testing Decisions

- The highest primary seam is the public Fusion Project application command and projection boundary. Tests issue creator actions and assert durable project state, next actions, blockers, stage readiness, and creator-facing projections rather than private helper calls or widget structure.
- Project-store tests remain a narrower supporting seam for atomic writes, schema rejection, managed/reference deletion semantics, trash/restore, and concurrent task checkpoints.
- Navigation tests verify startup, project creation, project refresh, explicit Project Workspace Mode entry, and explicit Traditional Compatibility Mode entry through externally visible page outcomes rather than internal Streamlit session keys.
- Task tests use durable status and input fingerprints to cover progress, interruption, retry, cancellation, concurrency, and stale-result admission.
- Workspace tests cover synchronized selection, queue ordering, decision persistence, undo, draft impact, version creation, comparison, and safe restoration.
- Render tests enter through Render Preflight and prove blockers disable rendering, warning reasons persist, passed checks allow rendering, and existing Render Outcomes are immutable.
- Planning reliability follows the dedicated P0 specification and reuses the existing public planning workflow as its principal seam.
- Existing Fusion Script Pipeline, Fusion Matching Workflow, Finalizer, Visual Evidence Artifact, resumable-task, stream-generation, and Streamlit orchestration tests are prior art.
- Visual acceptance records primary states at 1440p, 1080p, and 1024px and includes keyboard navigation, focus, contrast, long text, empty states, and error states.
- Real-media acceptance completes at least one creation-to-render usability sample before migration cutoff, followed by the broader three-material-classes-by-two quality set.
- A good test asserts creator-visible safety, persistence, or recovery behavior and remains valid if private modules or component layout are refactored.

## Out of Scope

- Building a full non-linear video editor or replacing the bounded synchronized review timeline with unrestricted editing.
- Rewriting the application as a separate React frontend or introducing a local API boundary during this delivery.
- Copying all Local Source Videos into project storage.
- Automatically grouping unrelated legacy tasks, evidence, scripts, or media into projects.
- Deleting referenced local source movies when a project is trashed or permanently removed.
- Allowing mobile to perform the full three-region evidence, timeline, or version-editing workflow.
- Redesigning ordinary commentary and documentary modes beyond preserving a legacy entry during migration.
- Making model reasoning, a composite quality score, or UI state the authority for renderability.
- Automatically resolving Evidence Conflicts, silently applying repairs, or silently invalidating approved work.
- Guaranteeing provider availability or always-valid LLM output; provider failures must instead be safely recoverable.
- Declaring Phase 3 complete from a static prototype, isolated components, or unit tests without a production project flow and real-media acceptance.

## Further Notes

- This specification is the `ready-for-agent` source of truth for the full project-centered UI. The detailed delivery design below preserves the page contracts, state model, migration sequence, implementation slices, and acceptance checklist agreed during planning.
- The project-centered ownership decision, gated workflow, Streamlit multipage boundary, and recoverable plan-attempt policy are recorded in the corresponding architecture decisions.
- The supplied dark project-library and two-column setup screenshots are visual references, not pixel-perfect component contracts.
- The existing conditional workspace and review services are reusable migration inputs, but their presence inside the legacy settings page does not satisfy this specification.
- The P0 planning-reliability behavior is specified separately and remains a release blocker for this UI.

## Detailed delivery design

## Product boundary

- One Fusion Project represents one intended commentary-video output.
- A project may contain an ordered sequence of multiple source videos, multiple evidence artifacts, multiple script versions, background tasks, review decisions, and immutable Render Outcomes.
- A project never silently groups unrelated legacy tasks or artifacts.
- Local Source Videos remain at their original filesystem paths and are referenced by identity; browser-uploaded files become Managed Project Assets.
- Deleting a project never deletes referenced Local Source Videos.
- Film Vision Fusion receives the new UI first. Ordinary commentary and documentary workflows remain available through a legacy-modes entry during migration.
- This is an evidence-oriented commentary workspace, not a full non-linear video editor.

## Experience principles

1. **Project first.** The project exists and autosaves before analysis or generation starts.
2. **One visible next action.** Every stage explains its prerequisite, current work, blocker, and next safe action.
3. **Inspect freely, mutate safely.** Users may inspect every Fusion Workflow Stage; actions remain gated by durable prerequisites.
4. **No browser-session ownership.** Refreshing or leaving a page cannot erase project, task, review, or version state.
5. **Evidence stays synchronized.** Selecting a review item aligns source video, timeline item, narration, Story Beat, Subtitle Evidence, and Visual Evidence.
6. **Drafts are not authority.** Content edits autosave as Content Drafts and affect downstream work only after impact confirmation.
7. **Renderability has one authority.** Render Preflight alone determines whether rendering is available.
8. **Operational language over technical noise.** Normal views say what happened, what was preserved, and what can be done; bounded diagnostics remain available separately.

## Visual direction

Use the supplied dark project-library and two-column setup references as visual direction, not as a component contract.

### Design tokens

- App background: near-black neutral (`#07090D` family), without pure-black cards.
- Primary surface: charcoal (`#14171C` family).
- Raised surface: slightly lighter charcoal with a one-pixel neutral border.
- Primary action: accessible blue; use teal for mode tags and success only.
- Warning: amber; blocker: red; inactive/disabled: neutral gray.
- Text: high-contrast warm white, secondary gray, subdued metadata gray.
- Radius: 10–14 px for cards and inputs; 8–10 px for buttons.
- Spacing: 8 px base system; content widths and gaps remain stable across pages.
- Status must always have text or an icon label; color is never the only signal.

### Shared shell

- Top bar: NarratoAI identity, current project breadcrumb when applicable, autosave state, global Task Center, theme control, system settings.
- Project pages do not reproduce the old three-column global settings layout.
- Global settings contain providers, credentials, FFmpeg, and application defaults.
- Project settings contain only values that belong to the current Fusion Project.
- The shell supports dark mode first and uses tokens that permit a later light theme without changing workflow components.

## Information architecture

```text
Project Library
├── All Projects
├── Running
├── Waiting for Review
├── Completed
└── Trash

New Fusion Project
└── Project configuration + source-video import

Fusion Project Workspace
├── Setup
├── Media & Evidence
├── Narration & Narrative Map
├── Picture Matching
├── Review
└── Output

Global Task Center
Legacy Creation Modes
System Settings
```

## Page specifications

### 1. Project Library

The application opens here by default.

Header controls:

- Search projects by name.
- Filter by All, Running, Waiting for Review, Completed, or Trash.
- Switch card/list presentation.
- Sort by latest activity, creation time, or name.
- Create New Project as the primary action.
- Open the global Task Center.

Project card:

- Thumbnail from the first available source frame or latest successful Render Outcome.
- Project name and Film Vision Fusion mode tag.
- Fusion Project Status and current Fusion Workflow Stage.
- Last activity time.
- Progress summary for running work.
- Blocker or pending-review count without raw technical text.
- Open action; archive/trash actions live in an overflow menu.

Empty state explains the project model and offers Create New Project or Import Existing Work.

Trash is recoverable. Permanent removal requires a second confirmation and lists exactly which Managed Project Assets, generated artifacts, Render Outcomes, and rebuildable caches will be removed. Referenced Local Source Videos are never included.

### 2. New Fusion Project

Create the durable draft project immediately when the page opens through the New Project action. Navigating away must not discard it.

Desktop layout follows the supplied two-column reference:

- Left configuration panel: project name, output language, commentary style, voice profile, target narration length, subtitle policy, Original Sound Ratio preference, optional background music, and advanced defaults.
- Right source panel: local-path selection and browser upload, supporting an ordered Source Video Sequence.
- Footer: readiness summary and Continue to Media & Evidence.

Each source-video row contains:

- Creator title and sequence position.
- Source type: Local Source Video or Managed Project Asset.
- File identity status, duration, resolution, and availability.
- Subtitle source and status.
- Existing Visual Evidence Artifact selection, if compatible.
- Include/exclude analysis toggle.
- Reorder and remove controls.

Local references persist path, identity, and metadata without copying the movie. Browser uploads are copied into project-managed storage. Moving or changing a referenced file produces an explicit offline/identity-changed state.

### 3. Fusion Project Workspace shell

The workspace always renders, even when the project has no task or artifact yet.

Top project bar:

- Back to Project Library.
- Project name and autosave status.
- Fusion Project Status.
- Current active version.
- Running-task summary.
- Global Task Center button.
- Project menu.

Stage rail:

1. Setup
2. Media & Evidence
3. Narration & Narrative Map
4. Picture Matching
5. Review
6. Output

Stages remain navigable for inspection. Each stage shows `ready`, `running`, `waiting`, `warning`, `blocked`, or `complete`; disabled actions state the missing prerequisite instead of disabling silently.

### 4. Media & Evidence

- Show every source independently with subtitle and Visual Evidence state.
- Display the Full-Film Analysis estimate before starting.
- Permit parallel visual analysis across different source videos.
- Show task progress, last activity, cancellation, recovery, and bounded diagnostics.
- Verify source identity before reusing a Visual Evidence Artifact.
- Support explicit import into a Migrated Fusion Project; never infer cross-task ownership.
- Completing analysis enables narration work but does not auto-start an unchecked chain.

### 5. Narration & Narrative Map

- Present approved evidence inputs and generation configuration before model work.
- Stream narration progress as waiting for first chunk, active, idle, timed out after progress, completed, failed, or cancelled.
- Preserve partial output only in diagnostics.
- Save narration edits as a Content Draft.
- Show generated Narrative Map alongside narration, with Story Beat navigation.
- Support edit, approve, or explicitly skip approval.
- Show invalidation impact before applying a Narrative Map draft.
- Provide “continue automatically to the next Review Checkpoint,” never unchecked one-click rendering.

### 6. Picture Matching

- Present the Fusion Segment Plan and its Plan Approval checkpoint.
- Show one row per Segment Match with source, Core Window, status, attempt, and recoverability.
- Allow targeted retry or creator-approved one-segment repair.
- Different source analyses may run concurrently, but only one content-mutating matching/finalization pipeline may be active per project.
- A completed task whose input version is no longer active becomes a Stale Task Result and cannot overwrite the project.

### 7. Review

Use a queue-first, desktop-first three-region layout.

Left region:

- Project-stage summary.
- Ordered review queue: blockers, high-value suggestions, informational audit.
- Filters by issue kind, source video, Story Beat, and status.
- Individual review for Evidence Conflicts, overlaps, failed Segment Matches, and post-progress timeouts.
- Batch confirmation only for explicitly low-risk findings.

Center region:

- Source-video preview bound to exact source identity and time range.
- Review-oriented timeline, not a full NLE.
- Matching narration and Story Beat display.
- Current selection and playback position remain synchronized.

Right region:

- Subtitle Evidence and Visual Evidence restricted to the selected Evidence Window.
- Highlight Candidates and Fusion Segment Plan context.
- Version comparison, Content Draft impact, review actions, and advanced diagnostics.
- Render Preflight summary remains visible when relevant.

Selecting an issue must update all three regions. If source identity, `_segment_id`, or time range cannot support a safe link, show `Cannot safely locate` and never guess.

Permitted timeline changes:

- Edit narration as a Content Draft.
- Adjust clip bounds only inside the owning Core Window.
- Adopt or remove a Highlight Candidate.
- Change a reviewable OST decision.
- Request one-segment rematching or repair.

Not permitted:

- Arbitrary cross-window replacement.
- Multi-track editing, filters, keyframes, or professional transitions.
- Automatic resolution of an Evidence Conflict.
- Direct mutation of an approved version without creating a draft and impact preview.

### 8. Output

- Render Preflight is the only render decision surface.
- Group blockers, overridable warnings, and passed checks.
- A warning override requires a persisted reason and supports undo before rendering.
- Rendering binds an immutable Fusion Script version, project-output settings snapshot, and Preflight record.
- Every successful render creates a Render Outcome; no output overwrites a previous outcome.
- Show preview, output path, creation time, bound version, duration, subtitle result, and export/open actions.
- The project card previews the latest successful Render Outcome while retaining history.

### 9. Global Task Center

Show all project-owned tasks with project name, task type, status, progress, last activity, failure category, and actions.

Task kinds:

- Visual analysis
- Narration generation
- Narrative Map generation
- Segment planning
- Segment matching
- Targeted repair
- Finalization
- TTS/subtitle preparation
- Rendering

Actions depend on durable status: open project, continue, cancel, retry affected unit, or view diagnostics. Leaving a project does not stop its tasks. Application restart changes orphaned running tasks to interrupted/recoverable rather than leaving them falsely running.

## Project and persistence model

Add a local project repository under `storage/fusion_projects/<project_id>/` with atomic JSON writes. A project record contains references rather than embedding large artifacts.

Required top-level fields:

```text
schema_version
project_id
name
mode
status
active_stage
created_at
updated_at
source_video_sequence[]
project_settings
artifact_refs
task_refs
active_version_id
review_decisions
render_outcomes
trash_state
```

`artifact_refs` includes an append-only `fusion_plan_attempts` collection. Each Fusion Plan Attempt records only its ID, input fingerprint, provider/model identity, received-character count, bounded/redacted response excerpt or project-local raw-response reference, parse result, Plan Validation Findings, repair linkage, status, timestamps, and diagnostic reference. It never stores API keys, full prompts, or hidden model reasoning.

Constraints:

- IDs are generated locally and are path-safe.
- Project records contain no API keys, raw full prompts, or hidden model reasoning.
- Source entries have stable source IDs; time ranges are always scoped to one source ID.
- Project status is derived from durable tasks, checkpoints, review findings, and Render Preflight—not from the selected page.
- Active stage is navigation preference, not evidence of completion.
- Every mutating task captures its input version/fingerprint.
- Task completion applies only when its captured input remains active; otherwise it is stored as a Stale Task Result.
- Content Drafts persist separately from active versions.
- Render Outcomes are immutable references to produced media and their provenance snapshot.
- A Fusion Plan Attempt is not an approved Fusion Segment Plan. Only a validated plan that passes the Plan Approval Review Checkpoint may be admitted to matching.

## Status and gating model

Fusion Project Status:

```text
draft
running
waiting_for_review
warning
blocked
ready_to_render
rendering
completed
archived
trashed
```

Status precedence:

1. trashed / archived
2. blocked
3. running / rendering
4. waiting_for_review
5. warning
6. ready_to_render
7. completed
8. draft

The implementation must define this precedence once in a project projection service. Pages may render the projection but may not reinterpret status independently.

Review Checkpoints:

- Analysis estimate confirmation
- Narration approval or explicit skip where supported
- Narrative Map approval/edit/explicit skip
- Fusion Segment Plan approval
- Individual high-risk Evidence Conflict review
- Content Draft impact confirmation
- Render Preflight
- Explicit render action

## Error and recovery language

Normal task errors follow this template:

```text
What happened
What completed work was preserved
What is blocked
Recommended next action
Available actions
```

Example:

```text
Picture matching timed out at segment 6 of 12.
Five completed Segment Matches were preserved.
Finalization and rendering are waiting for this segment.
[Continue this segment] [View diagnostics] [Cancel task]
```

Diagnostic drawers may show provider/model identity, timing, character counts, attempts, segment identity, and bounded partial text. They must not expose credentials, full prompts, or model chain-of-thought.

## Migration behavior

- Keep a temporary Film Vision Fusion option in the legacy creation-mode selector.
- Selecting it redirects to Project Library with an explanation; it no longer expands the old Fusion settings form.
- Provide Import Existing Work for compatible visual-analysis and Fusion Matching records.
- Import requires creator selection of related records and source videos.
- Imported records remain untouched; the Migrated Fusion Project stores references and migration metadata.
- Existing generated scripts may be imported as a starting version only after source identity and timeline validation.
- Remove the legacy entry only after project creation, task recovery, review, and rendering pass acceptance.

## Implementation seams

The implementation exposes four focused application seams:

- Project repository: atomic persistence, source/asset ownership, versions, trash, restore, and immutable outcomes.
- Project projection: status precedence, stage readiness, card summaries, blockers, and the next safe action.
- Project task coordinator: task ownership, concurrency, interruption recovery, input fingerprints, and stale-result admission.
- Workspace projection and commands: synchronized review context, durable decisions, drafts, invalidation previews, and preflight actions.

Streamlit pages cover Project Library, New Fusion Project, Fusion Project Workspace, and Task Center. Focused presentation components render the project shell, setup, evidence, narration, matching, review, and output projections through shared visual tokens.

The UI calls service-level commands and projections. It must not write project JSON directly, derive renderability, change task status, or decide invalidation inside Streamlit components.

## Ordered implementation plan

### P0 — Script Planning Reliability Gate

This is a release blocker before any project UI slice. It addresses the confirmed incident in which streaming completed with 17,241 characters, but a proposed segment exceeded the normal 3–8 narration-sentence range without the required `exception_reason`; structural validation raised before the existing continuity-only repair path could run. A separate event-loop cleanup defect emitted `Task was destroyed but it is pending!` after the response completed.

The implementation source of truth for this gate is `ready-for-agent-film-vision-fusion-script-planning-reliability.md`. The requirements below summarize its integration with the project-centered workspace and must not be implemented as a separate recovery policy.

#### Required behaviour

- Persist a Fusion Plan Attempt immediately after a stream completes, before JSON parsing or validation. A malformed, invalid, repaired, abandoned, or superseded attempt remains inspectable and cannot become match or render input.
- Replace raw `ValueError` propagation at the planning boundary with typed Plan Validation Findings. Each finding has a stable code, creator-safe summary, affected segment IDs or narration span where known, observed sentence span, and recovery class: `auto_repairable`, `creator_edit_required`, or `fatal`.
- Run exactly one targeted Plan Repair for repairable structural or continuity findings. The repair receives the parsed plan, current evidence-safe planning inputs, and the structured findings—including the missing `exception_reason` and offending range—not only continuity findings.
- A repair may split or rebalance a segment, or add a truthful explicit exception reason supported by the plan/evidence. The application must never locally invent an exception reason, silently waive the 3–8 sentence rule, or alter a creator-approved narration merely to pass validation.
- Validate the repaired result through the same parser and validator. If it passes, save it as a new linked attempt and present it for Plan Approval. If it fails, create a durable `waiting_for_review` state; do not raise a raw stack trace to the creator and do not silently restart the full narration generation.
- If the first response cannot be parsed, run at most one format-only repair using the original response and output schema. If that repair fails, preserve the attempt and offer a deliberate new plan-generation attempt; it must not overwrite the original attempt.
- The creator may open a safe structured plan editor, correct the affected ranges or explicit exception reason, then choose **Validate and continue**. The system validates before allowing Plan Approval; an invalid edited plan cannot enter matching, finalization, or rendering.
- The normal UI reports what completed, what is preserved, what is blocked, and the next action. It offers **Review plan**, **Retry repair** only when a fresh attempt is permitted, **Generate a new plan**, and **View diagnostics**. Advanced diagnostics redact sensitive data and show no Python traceback, credentials, full prompt, or model chain-of-thought.
- Every creator retry creates a linked Fusion Plan Attempt with its own request budget; it never overwrites prior diagnostic evidence. Automated work is bounded to one structural/continuity repair or one format-only repair per attempt.
- The async bridge must close provider streams/iterators in `finally`, shut down asynchronous generators before event-loop close, cancel and await remaining loop-owned tasks, and preserve a successfully received response if cleanup reports a secondary fault. Cleanup diagnostics are recorded without creating a pending-task warning in normal operation.

#### Acceptance tests

- A mocked plan with a 9-sentence segment and no `exception_reason` produces a structured finding, invokes exactly one targeted repair, validates the repaired plan, and reaches Plan Approval without a raw exception.
- A valid plan performs no repair. A repair that remains invalid is preserved as a linked attempt, reaches creator recovery, and cannot start matching.
- A malformed planner response is preserved before its single format-only repair; a second failure offers a new linked attempt rather than rerunning unrelated expensive work automatically.
- A creator edit cannot bypass parser, structural, continuity, approval, or Render Preflight checks.
- A subprocess test using a deliberately unfinished async generator proves bridge shutdown produces neither `Task was destroyed but it is pending!` nor an unclosed stream warning. Provider-stream tests cover success, cancellation, first-chunk timeout, post-progress timeout, total-budget expiry, and cleanup failure after a completed response.
- The existing end-to-end planning workflow renders a creator-safe recovery projection for all invalid-plan cases and never exposes a Python stack trace.

Exit: a provider can return malformed or structurally nonconforming plan text without losing it, leaking a pending async task, silently weakening evidence constraints, restarting unrelated work, or leaving the creator at a generic generation-error screen.

### Slice 0 — Freeze the legacy boundary

- Add a failing navigation test proving Film Vision Fusion opens Project Library.
- Add a visible temporary notice in the legacy selector.
- Prevent new Workspace logic from being added to the legacy settings component.

Exit: the target UI boundary is enforceable before migration work starts.

### Slice 1 — Fusion Project repository and projections

- Implement project schema, atomic store, list/search/sort, create, rename, autosave, archive, trash, restore, and permanent-delete plan.
- Implement Source Video Sequence and managed/reference ownership.
- Implement project status precedence and stage-readiness projection.
- Add source identity/offline detection.

Exit: a project survives refresh/restart and cannot delete a referenced source movie.

### Slice 2 — Project Library and new-project setup

- Build the dark shared shell and Project Library.
- Build card/list states, filters, empty states, and task badges.
- Build two-column new-project setup with ordered multi-video import.
- Migrate project-scoped narration, TTS, subtitle, OST, and output settings from the legacy form.

Exit: the user can create, reopen, configure, and safely trash a project without using the old Fusion form.

### Slice 3 — Media, evidence, and project-owned tasks

- Attach existing visual-analysis tasks and artifacts to project/source IDs.
- Add Full-Film Analysis estimates and source-by-source controls.
- Expand Task Center to all required task kinds.
- Implement global and project summaries, interruption recovery, and concurrency rules.

Exit: tasks continue across page navigation and restart with ownership and recovery intact.

### Slice 4 — Narration, Narrative Map, and matching stages

- Move narration generation and stream diagnostics into the project stage.
- Implement Content Draft storage and impact preview.
- Present Narrative Map review and Plan Approval checkpoints.
- Attach Fusion Matching Task snapshots and targeted recovery to project/version identity.
- Reject stale task completion from becoming active.

Exit: the complete pre-review pipeline runs within one durable project.

### Slice 5 — Production review workspace

- Build queue-first three-region layout.
- Implement selection synchronization across source video, timeline, narration, Story Beat, and evidence.
- Port persisted acknowledge/adopt/ignore/override/undo actions.
- Port version comparison and restore.
- Implement bounded timeline edits and one-segment repair.

Exit: every actionable review item is locatable or explicitly marked unsafe to locate.

### Slice 6 — Output, migration, and removal of old Fusion UI

- Build Output stage around Render Preflight.
- Create immutable Render Outcomes and render history.
- Implement Migrated Fusion Project flow.
- Redirect legacy Fusion selector to Project Library.
- Remove conditional Fusion Workspace rendering from the legacy form after parity verification.

Exit: one real project completes from creation to a playable final video without the legacy Fusion UI.

### Slice 7 — Visual and real-media acceptance

- Capture 1440p, 1080p, and 1024px reference screenshots for all primary states.
- Verify empty, running, waiting, blocked, ready, completed, offline-source, interrupted, and stale-result states.
- Run keyboard and contrast checks.
- Complete at least one end-to-end usability sample before migration cutoff.
- Then execute the broader three-classes-by-two real-media quality set required by the parent specification.

Exit: the UI and quality acceptance gates both have recorded evidence.

## Automated test requirements

Project store:

- Atomic create/read/update under concurrent task checkpoints.
- Invalid/path-traversing IDs rejected.
- Local references are not deleted.
- Managed assets require explicit destructive confirmation.
- Trash and restore preserve task/artifact/version references.
- Malformed or future-schema project records fail visibly.

Projection:

- Table-driven status precedence.
- Stage prerequisites and blocker messages.
- Project-card summary contains no sensitive request data.
- Refresh projection uses durable state, not prior session state.

Task ownership:

- Different-source analyses may run concurrently.
- Content-mutating tasks are serialized per project.
- Task input version/fingerprint is persisted.
- Old-version completion becomes Stale Task Result.
- Restarted running tasks become interrupted/recoverable.

Script planning reliability:

- Plan-attempt persistence occurs before parse, validation, repair, or UI projection.
- Table-driven validation findings cover malformed JSON, absent segments, gaps/overlaps, out-of-range sentence spans, and a 9-sentence segment without `exception_reason`.
- Structural and continuity repair both make one bounded, finding-specific repair request; valid plans make none.
- Invalid repair output reaches durable creator recovery and cannot become a matching input.
- Safe plan editing revalidates before Plan Approval and leaves prior attempts immutable.
- Async-loop and provider-stream cleanup tests assert no pending async-generator or unclosed-stream warnings for success, timeout, cancellation, and secondary cleanup failure.

Workspace:

- Selection synchronizes source ID, time range, `_segment_id`, Story Beat, narration, Subtitle Evidence, and Visual Evidence.
- Missing identity or segment mapping never falls back to a different source.
- Decisions persist and undo after refresh.
- Draft impact appears before apply.
- Applied drafts create versions and invalidate only dependent work.

Output:

- Blockers always disable render.
- Warning override reason persists.
- Render binds the selected active version and configuration snapshot.
- Existing Render Outcomes are not overwritten.

Navigation:

- App opens at Project Library.
- New Project creates a durable draft before upload.
- Legacy Fusion selector redirects rather than renders old controls.
- Project refresh returns to the same project and restores its durable projection.

## Manual acceptance checklist

The Phase 3 UI is complete only when all are true:

1. Application startup visibly opens Project Library.
2. A creator can create a draft project, refresh, and reopen it.
3. New-project setup uses the approved two-column configuration/media layout.
4. One project supports an ordered multi-video source sequence with per-source evidence state.
5. Six Fusion Workflow Stages are navigable and explain blocked actions.
6. A task continues after leaving its page and recovers after application restart.
7. Selecting a review issue synchronizes video, timeline, narration, Story Beat, and evidence.
8. Content Draft application shows impact and creates a version.
9. Render Preflight is the only render entry.
10. Each render creates a distinct Render Outcome.
11. The legacy Fusion selector no longer expands the old configuration page.
12. Normal creator flows expose neither `st.session_state`, raw JSON files, nor task IDs.
13. 1440p, 1080p, and 1024px visual acceptance is recorded.
14. At least one real source completes creation-to-render usability acceptance.
15. A structurally invalid plan is repaired or presented for creator correction without a raw exception, lost output, duplicate full-film generation, or pending-task warning.

## Explicit non-completion conditions

Phase 3 must not be reported complete when any of the following remains true:

- Fusion Project Workspace appears only after a matching task exists.
- Project state exists only in `st.session_state`.
- The old global settings page remains the primary Film Vision Fusion entry.
- Task Center omits required project task kinds.
- A review issue is shown without safe source/evidence synchronization.
- Render can start outside Render Preflight.
- Refresh loses project, draft, decision, version, or task ownership state.
- Only a static HTML prototype or unit-test projection exists without a production project flow.
- A planner validation failure can bypass a durable Fusion Plan Attempt, targeted recovery, Plan Approval, or creator-safe error presentation.
