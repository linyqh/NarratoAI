---
title: Film Vision Fusion review remediation
status: ready-for-agent
tracker: github
labels:
  - ready-for-agent
---

## Problem Statement

Film Vision Fusion's first deterministic-finalization release has passed its core tests, but review found six gaps. The legacy fallback can blur Visual Evidence into subtitle-derived story facts; invalid Highlight Candidates can disappear without an audit decision; acknowledged Evidence Conflicts cannot survive reuse; typed candidates become loose dictionaries inside finalization; the finalizer has too many unrelated responsibilities; and unrelated application, resource, CI, and test changes were mixed into the fusion change.

Creators and maintainers therefore cannot reliably explain every candidate decision, retain review acknowledgement, or safely reason about the boundary between on-screen facts and dialogue/story facts.

## Solution

Harden the existing Fusion Script Finalizer seam and its generation-result persistence boundary. Keep Visual Evidence labelled and separate in every path, carry typed candidate intake and rejection decisions through finalization, and make Evidence Conflict acknowledgement a durable domain state. Split the finalizer's internal policy collaborators without adding new user-facing flows. Restore a focused fusion change surface by separating unrelated changes into independently reviewable work.

## User Stories

1. As a creator, I want Visual Evidence to remain distinct from Subtitle Evidence in every generation path, so that on-screen observations are never presented as dialogue or plot facts.
2. As a creator, I want a fallback to preserve labelled Visual Evidence or fail transparently, so that a degraded provider path does not weaken evidence safety.
3. As a creator, I want every submitted Highlight Candidate to have a used, skipped, or rejected audit decision, so that no model output vanishes silently.
4. As a creator, I want malformed and out-of-batch Highlight Candidates rejected with a specific reason, so that I can diagnose bad visual-analysis output.
5. As a creator, I want candidate reasons to remain Visual Evidence-only, so that finalization never invents audio, dialogue, music, or off-screen facts.
6. As a creator, I want an acknowledged Evidence Conflict to stay acknowledged when I reopen or reuse a Fusion Script, so that I do not have to repeat review work.
7. As a creator, I want unresolved Evidence Conflicts to continue blocking unsafe candidate insertion, so that acknowledgement does not silently declare either source correct.
8. As a creator, I want both unresolved and acknowledged conflict states visible in the Finalization Report, so that the review state is auditable.
9. As a maintainer, I want Highlight Candidates to remain typed from artifact intake through finalization, so that validation, defaults, identity, and reasons have one owner.
10. As a maintainer, I want serialization limited to UI and persisted-audit boundaries, so that domain logic does not rely on repeated dictionary keys.
11. As a maintainer, I want finalization policy split into focused candidate-eligibility, timeline-policy, and report-projection collaborators, so that each rule can evolve without rewriting one coordinator.
12. As a maintainer, I want the public finalization seam to remain deterministic and unchanged in purpose, so that callers retain one place to obtain a finalized Fusion Script and Finalization Report.
13. As a reviewer, I want Fusion Script work isolated from unrelated rendering, TTS, network-security, resource, workflow, and unrelated-test changes, so that review scope remains trustworthy.
14. As an operator, I want no regression in the existing Original Sound Ratio, distribution, source identity, and Source Identity Waiver safeguards, so that this remediation does not weaken shipped behavior.

## Implementation Decisions

- Retain Fusion Script Finalization as the sole high-level seam. Its input boundary accepts validated Highlight Candidates plus intake rejections, and its result includes a complete candidate-decision ledger and structured Evidence Conflicts.
- Introduce a typed candidate-intake result that retains valid candidates and one rejection record for every invalid candidate. Artifact parsing must not silently discard malformed ranges, unsupported fields, or out-of-batch ranges.
- Keep Highlight Candidates typed throughout eligibility ranking, timeline insertion, and decision reporting. Convert them to mappings only when rendering a UI payload or writing a JSON audit artifact.
- Keep Visual Evidence in an explicitly named, independently labelled channel for both primary and fallback narration/matching paths. A fallback that cannot accept the channel must not concatenate it into Subtitle Evidence or plot analysis.
- Permit `EvidenceConflict` to represent only `unresolved` and `acknowledged` statuses, validate both at its domain boundary, and persist/reload that status with its original source identity, time range, evidence sides, and severity.
- Treat acknowledgement as a review-state record, not evidence verification. Only unresolved conflicts suppress conflicting narration claims and automatic candidate insertion; the report must retain both states.
- Split finalization internals behind focused collaborators for candidate eligibility/decision recording, timeline safety and insertion, and Finalization Report projection. The public coordinator only sequences these deterministic policies.
- Preserve the existing Original Sound Ratio formula, ±5 percentage-point tolerance, no-opening-OST=1 rule, bridge protection, no-three-consecutive-OST=1 rule, candidate source validation, and Visual Evidence audio-claim prohibition.
- Do not add new LLM calls, video analysis, audio inference, or UI workflows.
- Separate unrelated changes from the fusion remediation into independent reviewable commits or follow-up issues. Do not use this work to alter FFmpeg rendering, voice timing, URL trust policy, CI workflows, unrelated tests, or packaged audio/font resources.

## Testing Decisions

- Test externally observable behavior at the Fusion Script Finalizer and generation-result persistence seams; do not assert private helper implementation details.
- Extend existing finalizer and visual-artifact unittest suites with malformed, missing-field, and out-of-batch candidates. Assert an explicit rejected decision is retained for each input candidate.
- Add a fallback-path test proving Visual Evidence remains a separately labelled input and never appears inside Subtitle Evidence or plot-analysis fields.
- Add round-trip tests that acknowledge an Evidence Conflict, persist the generation result, reload/re-finalize it, and retain `acknowledged` without converting it to verified evidence.
- Verify unresolved conflicts still block automatic insertion while acknowledged conflicts remain visible in the report and do not erase either evidence side.
- Add behavior tests for typed candidate defaults, ranking, and serialization at the UI/audit boundary.
- Cover the public finalizer result before and after the internal collaborator split to ensure ratio, timeline, distribution, and report behavior remain deterministic.
- Use existing Fusion Script finalizer, visual-evidence artifact, and short-summary orchestration tests as prior art; add no production-only assertion fixtures.
- Validate scope separation with a diff review: remediation changes must be confined to fusion evidence/finalization and their tests/docs, while unrelated changes are independently tracked.

## Out of Scope

- Changing the semantics of OST=2, Original Sound Ratio, or post-render/TTS duration measurement.
- Building Audio Evidence, audio analyzers, or using Visual Evidence to infer sound.
- Replacing the editable script UI or reworking Visual Evidence Artifact compatibility/source-identity rules.
- Rewriting the previous commit's history or deleting user-approved packaged resources as part of this feature.
- Implementing unrelated rendering, TTS, networking, CI, or resource changes.

## Further Notes

- The remediation follows the review of commit `76bbd0b` against `3950ba5`.
- "Complete candidate audit" means one durable decision per submitted candidate, including candidates rejected before ranking.
- Acknowledgement is a user review state only; it never proves Subtitle Evidence or Visual Evidence correct.
