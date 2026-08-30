---
title: Film Vision Fusion reliability, narrative quality, and creator workspace
status: ready-for-agent
tracker: local
labels:
  - ready-for-agent
---

## Problem Statement

Film Vision Fusion has deterministic evidence and finalization safeguards, but creators can still encounter unsafe or confusing outcomes before an editable, render-ready commentary video is produced. Model-generated timelines can contain overlapping source ranges; a stream can visibly produce text in the UI but fail when its fixed total request budget expires; and the current UI exposes background work, approvals, conflicts, reports, and recovery states across transient session surfaces rather than one coherent project workspace.

The system also has limited deterministic support for the quality of a finished 3–10 minute horizontal film commentary. A creator can receive a technically valid result that repeats the picture, loses a character or causal handoff, inserts original-sound highlights for ratio rather than story value, or makes it hard to see which action is required next. These failures reduce trust, waste expensive generation work, and make safe manual review slower than necessary.

## Solution

Deliver three ordered improvements for Film Vision Fusion only:

1. **Reliability and safe renderability.** Make invalid timelines, failed Segment Matches, unresolved high-severity Evidence Conflicts, and incomplete streaming output explicit, recoverable states that cannot silently reach rendering. Provide local fixture-based verification and a reliable test command.
2. **Narrative quality.** Add a cached, creator-reviewable, evidence-bounded Narrative Map between approved narration and picture matching. It enables deterministic continuity and pacing checks plus user-approved, one-segment-at-a-time repair suggestions without inventing facts or rewriting the approved commentary wholesale.
3. **Creator workspace.** Replace the fragmented, one-shot review flow with a persistent Fusion Project Workspace. It presents project phase, live and resumable work, review queue, synchronized video/timeline/evidence inspection, version history, and Render Preflight in one desktop-first surface.

## User Stories

1. As a creator, I want overlapping source-video ranges rejected before rendering, so that a finished commentary does not replay or ambiguously cut the same footage.
2. As a creator, I want every authored timeline item validated against its source duration, so that invalid timestamps cannot reach the renderer.
3. As a creator, I want a failed or missing Segment Match to block rendering visibly, so that a partial story is never mistaken for a completed one.
4. As a creator, I want unresolved high-severity Evidence Conflicts to block rendering, so that disputed claims are not presented as facts.
5. As a creator, I want lower-risk warnings to be distinguishable from blockers, so that I can consciously decide when a creative trade-off is acceptable.
6. As a creator, I want a reason recorded when I render with a warning, so that later review can distinguish my choice from a system omission.
7. As a creator, I want a streamed request that produced partial text to be reported as incomplete progress rather than a generic API failure, so that I know what happened and can retry safely.
8. As a creator, I want to see whether a stream is waiting for its first chunk, active, idle, timed out after progress, or complete, so that long-running work is understandable.
9. As a creator, I want to retry only the timed-out Segment Match, so that I do not lose completed work or repeat expensive whole-film requests.
10. As a creator, I want incomplete streamed JSON preserved for diagnostics but excluded from matching, finalization, and rendering, so that partial output cannot become a broken script.
11. As a creator, I want a Narrative Map that identifies the active subject, pressure, trigger event, change, and next risk for each Story Beat, so that long-film commentary remains intelligible.
12. As a creator, I want the Narrative Map to use only Subtitle Evidence, Visual Evidence, and approved narration, so that it does not invent story facts or spoil the source.
13. As a creator, I want to inspect, edit, approve, or explicitly skip approval of the Narrative Map, so that I retain authorship over story interpretation.
14. As a creator, I want material changes to narration or evidence to invalidate only affected downstream work, so that safe reusable artifacts are retained.
15. As a creator, I want the system to flag missing causal bridges, unstable character references, repetitive narration, and story-irrelevant original-sound highlights, so that I can improve the viewing experience before rendering.
16. As a creator, I want repair suggestions to apply only to the affected segment after I approve them, so that the system never silently rewrites my reviewed commentary.
17. As a creator, I want a persistent project workspace, so that I can return after refresh or interruption without reconstructing the state of my work.
18. As a creator, I want an ordered review queue, so that I can resolve must-fix problems before spending time on optional polish.
19. As a creator, I want to click a conflict, quality warning, or candidate and jump to the exact source-video time range, so that I can judge the issue against the picture quickly.
20. As a creator, I want matching narration, timeline, subtitles, Subtitle Evidence, and Visual Evidence highlighted together, so that I can evaluate claims in context.
21. As a creator, I want edits to show their downstream invalidation impact before I apply them, so that no result disappears unexpectedly.
22. As a creator, I want review acknowledgements and low-risk decisions saved immediately with undo, so that refreshes do not lose audit work.
23. As a creator, I want editable narrative, timeline, and script changes to remain drafts until I apply them, so that I can review their impact deliberately.
24. As a creator, I want version history for original matches, finalized scripts, and repaired outputs, so that I can compare changes and restore context.
25. As a creator, I want a dedicated Task Center that survives page refresh, so that I can monitor, continue, cancel, or diagnose local background work.
26. As a creator, I want Render Preflight to separate blockers, overridable warnings, and passed checks, so that the render button is never ambiguous.
27. As an advanced creator, I want bounded diagnostic details without exposing internal model reasoning by default, so that I can troubleshoot without being overwhelmed by unreliable model traces.
28. As a maintainer, I want UI state projected through one focused workspace seam, so that Streamlit rendering does not duplicate orchestration and persistence policy.
29. As a maintainer, I want deterministic fixture tests and a small real-media acceptance set, so that reliability and viewing-quality regressions can be caught repeatedly.
30. As a maintainer, I want manual scorecards and structured feedback attached to sample outcomes, so that future quality work is based on observed creator and viewer experience.

## Implementation Decisions

- Implement in the stated phase order. Narrative and workspace work may depend on Phase 1 safety states but must not weaken existing evidence, source identity, Original Sound Ratio, or conflict safeguards.
- Keep Fusion Script Finalization deterministic. New model work for narrative quality happens before picture matching; Finalization itself continues to make no LLM, raw-video, or audio-inference calls.
- Expand authored-timeline validation to reject same-source overlapping ranges, invalid or non-positive ranges, and ranges outside known source durations. Existing opening, consecutive-OST, bridge, and conflict safeguards remain in force.
- Treat a failed, missing, malformed, or Core-Window-invalid Segment Match as non-renderable. Preserve completed Segment Matches and expose a targeted retry path.
- Classify stream failures by first-chunk wait, post-progress inactivity, total-budget expiry, provider response-format fallback, cancellation, and non-retryable provider error. Keep request first-chunk, inactivity, and total-budget controls separate.
- Retain partial stream output only as diagnostic data. It is never parsed as a successful Segment Match or included in a Fusion Script.
- Re-attempt a timed-out request only at the affected request or Segment Match, at most once automatically. A retry receives an independent request budget; the system does not silently restart a full film, silently rewrite approved narration, or consume completed work.
- Record structured stream diagnostics without API keys, full prompts, or other sensitive credentials. Include the generation phase, elapsed time, first-chunk latency, last-chunk age, received character counts, provider/model identity, segment identity, and attempt.
- Introduce Narrative Map as a cached, creator-reviewable, evidence-bounded domain artifact. A Story Beat records the related approved-narration span, evidence window, active subject, entering state, immediate goal or pressure, trigger event, exiting state, next risk or choice, temporal/location transition, and relevant warnings or conflicts.
- Generate Narrative Maps only from Subtitle Evidence, Visual Evidence, and approved narration. They cannot use external summaries, web research, model prior knowledge, inferred dialogue, inferred audio, hidden motives, or unsupported plot facts.
- Allow the creator to edit, approve, or explicitly skip Narrative Map approval. A skipped approval is audit state, not implicit approval.
- Compute invalidation from artifact dependencies. A material change displays affected results before commitment; Visual Evidence Artifacts and unrelated completed Segment Matches remain reusable when their identity and dependencies remain valid.
- Add deterministic narrative-quality checks for causal handoffs, active-subject changes, temporal/location jumps, repetitive narration, unstable character references, picture/narration density, and original-sound candidates that do not serve their Story Beat. These checks create review suggestions rather than opaque automatic render scores.
- Permit only creator-approved, evidence-window-bounded, one-segment repair for a narrative-quality finding. The repaired output re-enters normal matching, finalization, and preflight checks.
- Build a Fusion Project Workspace as the primary creator surface. It is a desktop-first, three-region workspace: phase and review queue, synchronized video/timeline, and contextual inspector for evidence, versions, and advanced diagnostics.
- The workspace uses a single UI projection seam that converts durable task, approval, Narrative Map, matching, Finalization, and preflight data into a stable creator-facing read model. UI components do not independently reinterpret orchestration rules.
- Represent project phase with explicit, durable statuses: not started, running, waiting for review, approved, warning, blocked, invalidated, and archived.
- Present review work in priority order: must-fix blockers, high-value suggestions, then informational audit entries. Low-risk items may be batch-confirmed; conflicts, timeline overlap, failed Segment Matches, and post-progress timeouts require individual review.
- Use synchronized source-video preview rather than a full non-linear editor. Selecting an issue, Story Beat, candidate, or timeline item locates the video and highlights related narration, subtitles, and evidence.
- Persist acknowledgement, adoption, ignore, and warning-override decisions immediately, with a short undo affordance. Hold content edits as drafts; applying a draft shows the invalidation plan and creates a new version.
- Maintain version history for original matched scripts, finalized scripts, repairs, and applied drafts. The active version is primary, while comparison shows changed beats, ranges, conflicts, ratio, and quality findings.
- Provide a durable Task Center for visual analysis, Narrative Map generation, segment planning, matching, targeted repair, and rendering. The workspace shows only the current project summary; Task Center shows all tasks, progress, last activity, recoverability, failure category, and actions.
- Hide raw model reasoning from normal creator workflows. Display actionable streaming state, activity timing, output quantity, and recovery guidance; put bounded raw stream excerpts and machine metadata in advanced diagnostics.
- Use Render Preflight as the sole creator-facing render decision. It groups results into must-fix blockers, warnings that require an explicit reason to override, and passed checks. Render is disabled while any blocker remains.
- Optimise the complete workspace for desktop. Mobile supports task monitoring, task recovery, and lightweight acknowledgement, but does not promise full evidence, timeline, or version editing.

## Testing Decisions

- Test externally observable safety and creator workflow behaviour at the authored-timeline validation, stream-generation result, Fusion Matching Task, workspace projection, and Render Preflight seams. Do not assert private helper structure or prompt wording.
- Add table-driven tests for overlapping same-source authored items, invalid ranges, source-duration overflow, failed or missing Segment Matches, and all non-renderable transitions.
- Use controlled async stream fakes to cover no-first-chunk timeout, stalled-after-progress timeout, total-budget timeout with emitted chunks, response-format fallback, cancellation, targeted retry, retained diagnostics, and rejection of partial output as script input.
- Test that stream retries receive a fresh budget and only the affected request retries. Verify completed Segment Matches and valid artifacts remain intact.
- Test Narrative Map caching, source/evidence identity compatibility, invalidation impact calculation, approval/skip state persistence, and evidence-bound output validation.
- Test quality findings against synthetic Story Beats and timelines: missing bridge, subject handoff, temporal jump, repeated narration, narration density warning, and story-irrelevant highlight suggestion.
- Test user-approved one-segment repair through its public matching/finalization path and verify it cannot change unrelated segments or bypass evidence and preflight safeguards.
- Add workspace-level tests for phase projection, queue ordering, desktop review states, targeted source-time selection, immediate acknowledgement persistence, draft application/invalidation confirmation, version comparison, and refresh/recovery.
- Add Render Preflight tests proving blockers disable rendering, warnings require stored reasons, and passed checks do not block rendering.
- Continue using existing Fusion Script Finalizer, Fusion Script Pipeline, Fusion Matching Workflow, visual-evidence artifact, local resumable-task, and Streamlit orchestration tests as prior art.
- Maintain a local real-media acceptance set outside version control. Commit only a sanitized manifest, expected assertions, and compact synthetic fixtures. For each of three material classes—dialogue-heavy, visual/action-heavy, and multi-video or non-linear—review at least two finished samples.
- Use a five-point human scorecard for opening attraction, character clarity, causal continuity, picture/narration fit, pacing, original-sound value, and ending completeness. No category may score below three and the average must be at least four before declaring Phase 2 quality acceptance.

## Out of Scope

- Replacing the editable commentary workflow with a full non-linear video editor.
- Using external movie databases, web search, summaries, or model prior knowledge to add plot facts, identities, motives, dialogue, audio, or endings.
- Automatically rewriting an entire approved commentary or silently restarting a full film after one Segment Match fails.
- Treating model reasoning or a composite quality score as the authority for renderability.
- Automatically resolving an Evidence Conflict by declaring one evidence source correct.
- Building audio evidence, music inference, or audio-value claims from Visual Evidence.
- Deep optimisation of vertical short-video presentation, mobile full editing, provider throughput, or unrelated ordinary-commentary and documentary workflows.
- Storing source media, full prompts, API keys, or sensitive model request content in version control or creator-feedback records.

## Further Notes

- This specification preserves the existing meaning of Subtitle Evidence, Visual Evidence, Evidence Conflict, Fusion Segment Plan, Fusion Matching Task, Original Sound Ratio, Finalization Report, and Narrative Bridge.
- Narrative Map, Fusion Project Workspace, Task Center, and Render Preflight are defined in the project glossary and should use those exact terms in implementation and user-facing documentation where appropriate.
- The existing three-variant review prototype is a design input only. Its winning decisions are a queue-first workspace, compact quality summary, and evidence-rich issue inspection; prototype code must be rewritten to production standards before adoption.
- Phase 1 establishes safe, reproducible execution; Phase 2 establishes evidence-bounded narrative quality; Phase 3 exposes both safely to creators. A later phase may separately address mobile and vertical-video experience after the desktop acceptance set is stable.
