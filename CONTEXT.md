# NarratoAI

NarratoAI turns source video and its accompanying evidence into timed narration scripts and rendered commentary videos. The script-generation context keeps dialogue-derived story facts separate from visually verified on-screen facts.

## Language

**Subtitle Evidence**:
Time-coded dialogue or transcription that establishes story, dialogue, and relationships.
_Avoid_: subtitle context, transcript facts

**Audio Evidence**:
Time-coded observations that independently establish audible dialogue, music, sound effects, or environmental sound.
_Avoid_: inferred sound, visual audio guess

**Visual Evidence**:
Time-coded observations extracted from source-video frames; it establishes only on-screen actions, people, objects, and locations.
_Avoid_: visual context, image facts

**Visual Analysis Prompt**:
The creator-provided instruction that directs frame observation and Highlight Candidate selection. It may prioritize visible subjects, actions, settings, objects, spatial relationships, and scene changes, but cannot request inferred audio, dialogue, motives, identities, or off-screen events.
_Avoid_: plot prompt, audio-analysis prompt

**Local Source Video**:
A source video stored on the same machine that runs NarratoAI and referenced by its filesystem path. It bypasses browser-upload size limits, while still requiring sufficient local disk space and decoding capacity.
_Avoid_: uploaded video, remote asset

**Managed Project Asset**:
A creator-uploaded source file copied into a Fusion Project's managed local storage. It belongs to the project lifecycle, unlike a Local Source Video that remains at its original path.
_Avoid_: local source reference, temporary upload

**Full-Film Analysis**:
The default visual-analysis scope for a Local Source Video. It examines the complete source timeline; a creator may narrow the range only as an explicit override.
_Avoid_: preview-only analysis, implicit sample

**Analysis Estimate**:
The pre-run projection of Full-Film Analysis duration, extracted-keyframe count, and visual-model request volume. A creator confirms this estimate before the task starts.
_Avoid_: guaranteed cost, hidden usage

**Resumable Visual Analysis**:
A Full-Film Analysis that persists completed batches against the Local Source Video identity and resumes only missing or failed batches after interruption.
_Avoid_: restart-only analysis, cross-video cache reuse

**Background Analysis Task**:
A Resumable Visual Analysis that continues on the local machine after a browser session refreshes or closes. Its state is persistently observable when the creator returns and it ends only when completed, failed, or explicitly cancelled.
_Avoid_: browser-bound job, abandoned request

**Visual Evidence Artifact**:
The persisted JSON record of Visual Evidence for one source video. It may be reused when its source identity is verified, or under a Source Identity Waiver.
_Avoid_: visual fusion JSON, frame-analysis cache

**Source Identity Waiver**:
An explicit acknowledgement that a legacy Visual Evidence Artifact has no persisted source identity and may be used only for downstream regression testing. It does not verify the source video.
_Avoid_: verified legacy import, compatibility bypass

**Highlight Candidate**:
A time-coded, visually supported recommendation to preserve source picture or performance as an OST=1 segment; it is optional evidence, not a mandatory script instruction.
_Avoid_: highlight result, original-clip command

**Original Sound Ratio**:
The share of a Fusion Script's selected timeline occupied by OST=1 source-video segments.
_Avoid_: dialogue ratio, model-estimated OST ratio

**Fusion Script**:
A timed narration script generated from Subtitle Evidence and Visual Evidence, with conflicts withheld for review.
_Avoid_: hybrid script, combined script

**Fusion Segment Plan**:
An ordered, reviewable plan that assigns contiguous portions of an approved narration to bounded source-time windows and narrative roles before a Fusion Script is matched.
_Avoid_: full-script plan, shot list

**Fusion Plan Attempt**:
A durable record of one completed plan-generation response and its parsing, validation, and bounded-repair outcome. It is recovery evidence, not an approved Fusion Segment Plan and cannot be used for matching or rendering.
_Avoid_: pending plan, failed prompt

**Plan Validation Finding**:
A deterministic, structured reason that a proposed Fusion Segment Plan is not admissible, including the affected segment where known and its available recovery action.
_Avoid_: generic exception, model error

**Narrative Map**:
A creator-reviewable, cached, evidence-bounded map of Story Beats, active subjects, goals, trigger events, risks, and time or location changes. It is created before narration-to-picture matching to improve continuity, but never establishes facts beyond Subtitle Evidence, Visual Evidence, and approved narration.
_Avoid_: plot invention, external synopsis, final script

**Evidence Window**:
The time-bounded subset of Subtitle Evidence, Visual Evidence, and Highlight Candidates available to one Fusion Segment Plan entry.
_Avoid_: global context, evidence chunk

**Segment Match**:
A timed local-script result generated for one Fusion Segment Plan entry from its Evidence Window.
_Avoid_: partial script, match fragment

**Plan Approval**:
The creator's explicit confirmation of a Fusion Segment Plan before its Segment Matches may consume model requests.
_Avoid_: automatic plan continuation, script approval

**Fusion Matching Task**:
A resumable local background task that persists an approved Fusion Segment Plan and the status and output of each Segment Match.
_Avoid_: foreground matching, browser-bound script generation

**Fusion Project**:
The durable container for one intended commentary-video output, including one or more source videos, configuration, evidence artifacts, background tasks, review decisions, script versions, and rendered outcomes.
_Avoid_: task, browser session, folder

**Project Library**:
The creator-facing collection of Fusion Projects and migrated legacy work, organised by status and recent activity.
_Avoid_: task list, file browser

**Migrated Fusion Project**:
A Fusion Project created explicitly from compatible legacy tasks or evidence artifacts without guessing relationships between unrelated legacy records.
_Avoid_: automatic migration, legacy task

**Fusion Workflow Stage**:
One navigable area of a Fusion Project—setup, evidence, narration and Narrative Map, matching, review, or output. A stage may be inspected freely, while actions inside it remain gated by durable prerequisites.
_Avoid_: project status, rigid wizard step

**Fusion Project Status**:
The current overall condition of a Fusion Project, such as running, waiting for review, blocked, ready to render, completed, or archived.
_Avoid_: workflow stage, selected page

**Source Video Sequence**:
The creator-defined ordered set of source videos belonging to a Fusion Project. Evidence windows and timestamps remain scoped to one member of the sequence.
_Avoid_: upload list, global timeline

**Content Draft**:
An autosaved but unapplied edit to approved narration, a Narrative Map, or a Fusion Script timeline. Applying it requires an impact preview and creates a new version.
_Avoid_: live edit, approved version

**Stale Task Result**:
The completed output of a background task whose input version is no longer active. It remains inspectable but cannot replace the current project state without an explicit creator decision.
_Avoid_: latest result, failed task

**Review Checkpoint**:
A creator decision boundary that must be satisfied before dependent work can continue, such as an analysis estimate, Narrative Map, Fusion Segment Plan, Evidence Conflict, or Render Preflight.
_Avoid_: modal, background task

**Render Outcome**:
An immutable rendered-video result bound to one Fusion Script version, output-settings snapshot, and Render Preflight record.
_Avoid_: current video, overwritten export

**Fusion Project Workspace**:
The creator's persistent primary surface for one Fusion Project, showing its current version, active background work, required reviews, evidence, timeline, and render readiness.
_Avoid_: one-shot wizard, transient session page

**Task Center**:
A durable view of Background Analysis Tasks, Fusion Matching Tasks, retries, and render work, including their progress, last activity, recoverability, and actionable failure state.
_Avoid_: toast-only progress, hidden background job

**Fusion Stream Snapshot**:
The transient, current-attempt progress of a Fusion planning or Segment Match request, including its phase and received model text; it is not an approved plan, Segment Match, or renderable output.
_Avoid_: streaming result, resumable script, final response

**Core Window**:
The non-overlapping source-time range assigned to one Fusion Segment Plan entry; its Segment Match may emit clips only inside this range.
_Avoid_: match range, segment context

**Context Window**:
The small source-time margin adjacent to a Core Window that supplies narrative context but cannot contribute emitted clips.
_Avoid_: overlap range, extra clip range

**Evidence Conflict**:
A validated record of a time window in which Subtitle Evidence and Visual Evidence cannot safely support the same narration claim; it carries source identity, both evidence statements, severity, and review status.
_Avoid_: model disagreement, mismatch

**Finalization Report**:
An audit of a Fusion Script's Original Sound Ratio, Highlight Candidate decisions, distribution, and unresolved Evidence Conflicts before rendering.
_Avoid_: render report, model explanation

**Render Preflight**:
The creator-facing classification of a current Fusion Script into must-fix blockers, warnings that require an explicit reason to override, and checks that have passed before a render may begin.
_Avoid_: generic error modal, automatic quality score

**Story Beat**:
A causally complete unit of a Fusion Script that states the active character or group, its immediate goal or pressure, the event that changes that state, and the resulting next risk or choice.
_Avoid_: highlight, arbitrary clip group

**Narrative Bridge**:
A narration-led source-video segment that makes an otherwise discontinuous change of time, place, character state, goal, or causal relationship understandable before the next Story Beat or Highlight Candidate.
_Avoid_: filler, transition effect

**Continuity Gate**:
A local validation that prevents a Fusion Script from entering the renderable state when an unmarked large source-time jump or Story Beat lacks the required Narrative Bridge.
_Avoid_: pacing preference, highlight quota
