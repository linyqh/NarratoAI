---
title: Film Vision Fusion deterministic finalization
status: ready-for-agent
tracker: local
labels:
  - ready-for-agent
---

## Problem Statement

Film Vision Fusion can generate visually grounded Highlight Candidates, but the generated Fusion Script still relies on prompt compliance for its original-sound ratio, candidate distribution, and Evidence Conflict handling. A model may silently skip conflicts, exclude valuable scenes without subtitles, cluster OST=1 segments in one part of the story, or miss the requested original-sound ratio without a deterministic correction step. The visual-analysis concurrency default was also raised outside this feature's intended scope.

## Solution

Introduce a deterministic Fusion Script Finalizer between script matching and user review. It validates the generated timeline, records Evidence Conflicts, admits visually supported no-dialogue highlights, measures the OST=1 duration ratio, and supplements the script from eligible Highlight Candidates when the ratio or story distribution is deficient. It never invents evidence or forces an unsafe candidate merely to reach a number. The user receives the finalized script together with a report explaining conflicts, candidate decisions, achieved ratio, and any unmet target.

The authoritative Original Sound Ratio is the sum of source-video durations of OST=1 timeline items divided by the sum of source-video durations of all finalized timeline items. A result is compliant when it is within five percentage points of the requested ratio. Rendered/TTS audio duration may be reported separately for diagnosis but does not drive automatic correction.

## User Stories

1. As a creator, I want the requested Original Sound Ratio checked from actual timeline durations, so that it is not merely an instruction to the language model.
2. As a creator, I want a result within five percentage points of my requested ratio, so that the final edit reflects my setting predictably.
3. As a creator, I want eligible Highlight Candidates inserted automatically when OST=1 is materially deficient, so that valuable source moments are not lost because the model undershot the target.
4. As a creator, I want an explicit warning when no safe combination of candidates can meet the ratio, so that the system does not hide an unmet target.
5. As a creator, I want the achieved ratio and requested ratio shown together, so that I can judge the result before rendering.
6. As a creator, I want the opening segment to remain OST=0 even during automatic supplementation, so that the narration hook is preserved.
7. As a creator, I want narration bridge segments preserved across story or source-video transitions, so that ratio correction does not damage continuity.
8. As a creator, I want no three-or-more consecutive OST=1 segments after correction, so that the result remains a narrated edit rather than a clip compilation.
9. As a creator, I want inserted candidates to avoid overlapping existing timeline items, so that source footage is not duplicated or cut ambiguously.
10. As a creator, I want candidates with unresolved Evidence Conflicts excluded from automatic insertion, so that correction never promotes disputed facts.
11. As a creator, I want high-value scenes without subtitles to remain eligible for OST=1, so that action, performance, reactions, and visual spectacle are not filtered out by a dialogue requirement.
12. As a creator, I want no-dialogue eligibility to rely only on Visual Evidence, so that the system does not fabricate dialogue, sound effects, music, or off-screen events.
13. As a creator, I want candidates ranked by explicit story importance, visual impact, and performance value, so that automatic choices are explainable.
14. As a creator, I want audio value represented as unknown when no independent Audio Evidence exists, so that a visual model's guess is never presented as an audio fact.
15. As a creator, I want candidate-level time ranges rather than whole analysis-batch ranges, so that inserted source clips are precise.
16. As a creator, I want malformed or out-of-batch candidate ranges rejected, so that invalid model output cannot reach the timeline.
17. As a creator, I want at least three Highlight Candidates used across the beginning, middle, and end thirds when the target, duration, and available candidates permit it, so that high points are not clustered.
18. As a creator, I want the three-candidate rule to degrade to the number of eligible candidates for short or sparse material, so that impossible quotas do not block generation.
19. As a creator, I want a report showing which candidates were used, skipped, or rejected and why, so that automated editing remains auditable.
20. As a creator, I want Subtitle Evidence and Visual Evidence disagreements retained as Evidence Conflicts, so that they do not disappear when the model avoids a time range.
21. As a creator, I want every Evidence Conflict to show its time range, subtitle claim, visual observation, severity, and status, so that I can understand what disagreed.
22. As a creator, I want script generation to continue when conflicts exist, so that I can review a useful draft instead of being blocked globally.
23. As a creator, I want unresolved conflict claims withheld from picture descriptions and narration assertions, so that the draft does not present disputed information as fact.
24. As a creator, I want conflicts displayed beside the Fusion Script before rendering, so that review happens at the point where I can still edit the result.
25. As a creator, I want the original matched script retained for audit, so that I can distinguish model output from deterministic finalization changes.
26. As an operator, I want visual-analysis concurrency to default to two, so that enabling highlights does not unexpectedly multiply API load.
27. As an advanced operator, I want to raise concurrency explicitly, so that controlled environments can trade rate-limit risk for speed.
28. As a maintainer, I want finalization to be deterministic and independent of another LLM call, so that the same inputs always yield the same validation report and supplemented script.
29. As a maintainer, I want legacy artifacts without structured scoring to remain readable with conservative defaults, so that reuse compatibility is preserved without treating missing values as strong evidence.
30. As a maintainer, I want finalization failures to leave the matched script recoverable, so that an invalid candidate cannot destroy otherwise useful work.

## Implementation Decisions

- Add one high-level Fusion Script Finalizer seam. Its input is the matched Fusion Script, requested Original Sound Ratio, normalized Highlight Candidates, Evidence Conflicts, and source-video timeline metadata. Its output contains the finalized Fusion Script and a Finalization Report.
- Keep the model-produced script immutable. The finalizer returns a new script and records every inserted, retained, skipped, or rejected decision.
- Define Original Sound Ratio as `OST=1 source duration / total finalized source duration`. OST=2 is not counted as pure original sound for this feature.
- Treat a ratio as compliant when its absolute difference from the requested ratio is at most five percentage points. A requested ratio of zero prohibits automatic OST=1 insertion.
- When below tolerance, choose eligible unused candidates deterministically by conflict safety, timeline validity, story-third deficit, total score, then chronological order. Stop once the lower tolerance boundary is reached or no eligible candidate remains.
- Do not automatically remove OST=1 segments when the result exceeds the upper tolerance boundary in the first release. Report the excess for user review because deletion can remove authored story beats. This asymmetry must be visible in the report.
- An inserted candidate becomes a standard OST=1 script item with a generated stable identifier, exact candidate time range, visual reason as its picture description, and the established original-clip narration marker.
- Reject insertion when a candidate overlaps an existing item from the same source video, lies outside its source duration, intersects an unresolved Evidence Conflict, would become the first item, creates three consecutive OST=1 items, or removes a required transition bridge.
- Partition the finalized story order into beginning, middle, and end thirds by cumulative timeline duration. When at least three eligible candidates exist and the requested ratio is greater than zero, prefer one eligible candidate per third before adding further candidates.
- Report distribution as achieved, degraded, or unavailable. Degraded means fewer than three eligible candidates existed; it is not an error.
- Extend Highlight Candidate signals with bounded `story_importance`, `visual_impact`, and `performance_value` scores. Keep `category`, `reason`, overall `score`, exact time range, and source-video identity. Missing legacy signals receive conservative neutral values and are marked inferred/defaulted in the report.
- Do not let Visual Evidence populate an audio-value score. Audio value is unknown unless a future independent Audio Evidence source supplies it. OST=1 may still preserve the clip's real audio; the selection reason remains visual.
- A no-dialogue candidate does not require Subtitle Evidence. Subtitle Evidence may strengthen or conflict with it, but absence of subtitles is not rejection.
- Represent Evidence Conflicts as structured records containing source-video identity, exact time range, subtitle claim, visual observation, severity, status, and optional related script item/candidate identifiers.
- Conflict statuses are unresolved and acknowledged. This release supports review and acknowledgement; it does not ask users to declare either source universally correct.
- Matching must return detected conflicts rather than silently dropping them. The finalizer withholds unresolved conflicting claims and candidates while allowing unaffected script items to proceed.
- Persist the original matched script, finalized script, Finalization Report, and Evidence Conflicts together in the generation result so reuse and audit do not depend on transient UI state.
- Show the report and conflict list in the Film Vision Fusion review UI before rendering. Users can inspect reasons and acknowledge conflicts; acknowledgement does not retroactively verify either evidence source.
- Restore the default visual-analysis concurrency to two. Keep the existing explicit advanced configuration as the only way to increase it.
- The finalizer must not call an LLM, inspect raw video frames, synthesize Audio Evidence, or mutate the persisted Visual Evidence Artifact.

## Testing Decisions

- Test through the Fusion Script Finalizer seam wherever possible. Tests assert the returned script and report, not private ranking helpers or internal data structures.
- Use table-driven unit tests with synthetic timelines and candidates so duration arithmetic, tolerance boundaries, ordering, and rejection reasons remain deterministic.
- Cover requested ratios of 0%, values whose outputs land exactly at both ±5pp boundaries, deficits with enough candidates, deficits without enough candidates, and outputs already above the upper boundary.
- Verify supplementation chooses candidates across beginning, middle, and end before taking a second candidate from an already covered third.
- Verify short and sparse inputs produce a degraded distribution report rather than an impossible hard failure.
- Verify no-dialogue candidates can be inserted without Subtitle Evidence and cannot assert dialogue, music, sound effects, or off-screen facts.
- Verify candidates are rejected for malformed ranges, out-of-source ranges, overlaps, unresolved conflicts, opening placement, bridge damage, and excessive consecutive OST=1 segments.
- Verify an Evidence Conflict survives matching/finalization with both evidence sides intact and is visible in the generation result.
- Verify unresolved conflict claims are absent from finalized picture/narration text while unrelated items remain unchanged.
- Verify legacy Highlight Candidates receive conservative defaults and remain eligible only when their existing fields and time range are valid.
- Verify finalization is idempotent: finalizing an already finalized result produces no additional inserted items and the same ratio/report decisions.
- Verify the original matched script is unchanged after successful and failed finalization.
- Add a UI-level orchestration test at the highest practical Streamlit seam to confirm the Finalization Report and Evidence Conflicts are placed into review state before rendering.
- Follow existing unittest conventions used by visual-evidence and short-summary services. Avoid tests that merely assert prompt wording; deterministic behavior must be demonstrated through outputs.
- Add a configuration regression test confirming the default concurrency is two and an explicit higher value is honored.

## Out of Scope

- Building a waveform, speech, music, or environmental-sound analyzer and introducing Audio Evidence.
- Using rendered TTS/audio duration as the authoritative ratio or automatically re-running correction after video encoding.
- Automatically deleting authored OST=1 segments when the ratio is too high.
- Asking an LLM to repair a failed deterministic finalization.
- Replacing the existing user-editable script table or changing the meaning of OST=2.
- Reworking visual artifact v2/v3/v4 compatibility and source-identity reuse rules already addressed by the preceding change.
- Adaptive concurrency based on provider limits or throughput benchmarking.

## Further Notes

- “Final” in Fusion Script Finalizer means ready for user review and rendering, not already encoded media.
- The Finalization Report should make partial success explicit: requested ratio, achieved ratio, tolerance, inserted candidates, rejected candidates with reasons, distribution status, and unresolved conflict count.
- The ratio guarantee is conditional on eligible footage. Safety and narrative constraints take precedence over numerical compliance.
- This specification resolves the remaining Standards and Spec findings from the visual-highlighting and visual-evidence-reuse reviews. The already-landed visual-only prompting, typed Highlight Candidate, exact candidate range, artifact-version allowlist, and per-generation source revalidation are prerequisites rather than work to repeat.
