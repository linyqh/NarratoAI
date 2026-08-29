# Segmented fusion-script matching

For long-film Fusion Scripts, NarratoAI will create a reviewable Fusion Segment Plan before matching, then generate ordered Segment Matches from bounded Evidence Windows and finalize them locally. This deliberately replaces one full-context matching call so long timelines can retain narrative coverage, localize failures, and reuse Visual Evidence Artifacts without another vision-model run.

The creator approves the plan before matching begins. A Segment Match normally covers 3-8 narration sentences, with a 30-90 second source-time range as a soft target; a narrative boundary may require an explicit exception.

Matching runs as a resumable local background task. A failed Segment Match is retried once automatically, then remains visible for an explicit retry; NarratoAI never silently finalizes a script that omits a failed planned segment.

Adjacent Segment Matches may receive a small Context Window on either side of their non-overlapping Core Window, but may emit clips only inside the Core Window. A material narration edit invalidates the Fusion Segment Plan and all Segment Matches while leaving its evidence inputs reusable.

NarratoAI runs at most two Segment Matches concurrently by default. When every planned segment succeeds, it automatically invokes the existing Finalization Report; unresolved Evidence Conflicts or failed segments keep the result out of the renderable state.

## Considered Options

We rejected retaining one full-film match because its subtitle, narration, and visual-evidence context grows beyond a reliable reviewable unit. We also rejected splitting the source video into arbitrary halves because it loses narrative continuity and does not give each match a purposeful evidence boundary.
