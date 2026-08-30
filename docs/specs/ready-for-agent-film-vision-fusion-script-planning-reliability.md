---
title: Film Vision Fusion script-planning reliability gate
status: ready-for-agent
tracker: local
labels:
  - ready-for-agent
---

## Problem Statement

Film Vision Fusion can spend many minutes successfully streaming a large Fusion Segment Plan response and then discard the usable result because one segment violates a deterministic schema rule. In the confirmed incident, the provider completed a 17,241-character response, but one proposed segment covered more than the normal 3–8 narration sentences without an explicit `exception_reason`. Structural validation raised before the existing continuity-repair path ran, so the creator received a generic script-generation failure and could neither inspect nor correct the plan.

The same request lifecycle can close its bridge-owned event loop while an asynchronous generator is still being finalized, producing `Task was destroyed but it is pending!`. This warning is a separate cleanup defect: it does not explain the invalid plan, but it indicates that completed, timed-out, or cancelled streams are not consistently releasing their resources.

Large prompts, long outputs, many evidence constraints, and sentence-boundary ambiguity can increase the probability that an LLM omits a required field or violates a local rule. They are risk factors, not the application failure's root cause. Provider output is inherently fallible; NarratoAI must preserve, classify, repair, and safely expose nonconforming output instead of assuming every response is valid or surfacing a raw exception.

## Solution

Introduce a P0 Script Planning Reliability Gate before the new project workspace is considered releasable. Every completed planning response becomes a durable Fusion Plan Attempt before parsing. Parsing, structural validation, and continuity validation produce creator-safe Plan Validation Findings rather than uncaught exceptions.

For a parsed plan with repairable findings, NarratoAI performs exactly one targeted Plan Repair using those findings. For an unparseable response, NarratoAI performs at most one format-only repair. A repaired result passes through the same validation path. If it remains invalid, the project enters a durable review state where the creator can inspect a safe structured representation, edit affected fields, validate again, create a new linked attempt, or abandon the attempt without losing prior work.

Only a validated Fusion Segment Plan that passes Plan Approval may start Segment Matching. Invalid attempts never become matching, finalization, or rendering input. Provider streams and bridge-owned asynchronous resources are closed deterministically on success, timeout, cancellation, validation failure, and secondary cleanup failure.

## User Stories

1. As a creator, I want a completed planning response saved before validation, so that a long-running model result is not lost because one field is invalid.
2. As a creator, I want plan-generation progress distinguished from plan validity, so that “the model responded” is not confused with “the plan is approved.”
3. As a creator, I want an invalid segment identified by segment and narration span, so that I know exactly what needs attention.
4. As a creator, I want the interface to explain the violated rule in plain language, so that I do not have to interpret a Python exception.
5. As a creator, I want a repairable structural error repaired once automatically, so that a small omission does not force another full generation.
6. As a creator, I want continuity and structural findings handled by the same bounded recovery flow, so that recovery does not depend on which validator ran first.
7. As a creator, I want malformed JSON to receive at most one format-only repair, so that formatting mistakes are recoverable without an uncontrolled retry loop.
8. As a creator, I want failed repairs preserved as linked attempts, so that I can compare what changed and diagnose recurring provider problems.
9. As a creator, I want to edit an invalid plan in a safe structured editor, so that I can resolve an obvious range or reason error myself.
10. As a creator, I want manual edits validated before they become authoritative, so that an edit cannot bypass safety constraints.
11. As a creator, I want to supply an explicit exception reason when a narrative boundary genuinely requires a segment outside the normal range, so that deliberate exceptions remain auditable.
12. As a creator, I want the system never to fabricate an exception reason, so that validation cannot be satisfied with invented justification.
13. As a creator, I want the system to split or rebalance an oversized segment only when the resulting plan still respects evidence and coverage, so that a mechanical fix does not damage the story.
14. As a creator, I want a new retry to create a separate attempt, so that prior output and diagnostics are not overwritten.
15. As a creator, I want unrelated narration and evidence work preserved when plan repair fails, so that I do not pay for or wait through completed work again.
16. As a creator, I want invalid plans blocked from Segment Matching, so that expensive downstream requests cannot consume unsafe input.
17. As a creator, I want invalid plans blocked from finalization and rendering, so that recovery safeguards cannot be bypassed later.
18. As a creator, I want Plan Approval to remain mandatory after automatic repair, so that a repaired plan is not silently accepted on my behalf.
19. As a creator, I want an invalid-plan screen to state what completed, what was preserved, what is blocked, and what I can do next, so that the failure feels recoverable.
20. As a creator, I want normal diagnostics to omit credentials, full prompts, and hidden model reasoning, so that troubleshooting does not expose sensitive information.
21. As an advanced creator, I want provider, model, timing, character count, attempt, and bounded response diagnostics, so that I can distinguish model-format problems from timeouts.
22. As a creator, I want leaving or refreshing the page to preserve the current attempt and review state, so that browser navigation cannot erase recovery work.
23. As a creator, I want cancellation to close the active stream cleanly, so that the application remains stable after I stop a request.
24. As a creator, I want a timeout after partial progress reported separately from an invalid completed plan, so that I choose the correct recovery action.
25. As a creator, I want a successfully received response preserved even if resource cleanup reports a secondary fault, so that cleanup does not turn success into data loss.
26. As a maintainer, I want parser, structural, and continuity failures represented by stable finding codes, so that UI and recovery policy do not depend on exception text.
27. As a maintainer, I want one public planning-workflow result to represent success, waiting for review, cancellation, and failure, so that presentation code does not reconstruct orchestration policy.
28. As a maintainer, I want repair requests bounded to one per attempt, so that malformed provider output cannot create an infinite or unexpectedly expensive loop.
29. As a maintainer, I want every repair linked to its source attempt and input fingerprint, so that stale results cannot overwrite current project state.
30. As a maintainer, I want provider streams and asynchronous generators closed under every terminal path, so that no pending task survives event-loop shutdown.
31. As a maintainer, I want regression coverage for the confirmed 9-sentence missing-reason case, so that validator ordering cannot reintroduce the incident.
32. As a maintainer, I want LLM nonconformance treated as expected boundary input, so that model complexity is managed by application resilience rather than prompt optimism.

## Implementation Decisions

- This specification is a P0 release blocker for the three-phase Film Vision Fusion delivery and precedes all project-workspace implementation slices.
- A Fusion Plan Attempt is persisted immediately when a planning stream completes and before parsing, structural validation, continuity validation, repair, or UI projection.
- A Fusion Plan Attempt is append-only recovery evidence. It records stable identity, project and input-version linkage, provider/model metadata, received-character count, timestamps, parse status, findings, repair linkage, bounded/redacted diagnostics, and terminal status.
- Attempt records exclude API keys, credentials, full prompts, hidden model reasoning, and unrestricted raw provider content. A project-local response reference or bounded excerpt may be retained according to existing diagnostic policy.
- Plan Validation Findings replace exception-text contracts at the planning boundary. Each finding contains a stable code, creator-safe summary, affected segment or narration span where known, observed value, expected constraint, and recovery class.
- Finding categories cover malformed JSON, invalid top-level shape, absent or malformed segments, sentence gaps or overlaps, indexes outside narration bounds, segments outside the normal 3–8 sentence range without a reason, invalid source windows, and continuity failures.
- A completed planning workflow returns a domain result such as validated, waiting for review, cancelled, or failed. UI code consumes this result and does not catch raw validation exceptions to infer state.
- Parsed plans with repairable structural or continuity findings receive exactly one targeted Plan Repair. The repair input includes the complete structured finding set rather than continuity findings alone.
- A plan that cannot be parsed receives at most one format-only repair. Format repair may restore the agreed schema but may not alter approved narration, add unsupported story facts, or waive evidence constraints.
- Every repaired response creates a linked Fusion Plan Attempt and passes through the same parser and validators as the original response. No dedicated “repair validator” may weaken the rules.
- Repair may split or rebalance a segment, or supply a truthful explicit exception reason grounded in the existing plan and evidence. NarratoAI never creates a generic local exception reason merely to make validation pass.
- A failed repair results in a durable waiting-for-review checkpoint rather than an uncaught error or automatic full-workflow restart.
- The creator may edit only the safe structured plan representation. Applying an edit creates a linked attempt and invokes normal validation before Plan Approval becomes available.
- A creator-initiated new generation creates a fresh linked attempt with an independent request budget. It preserves narration, evidence, previous attempts, and unrelated completed work.
- Only a validated plan may be offered for Plan Approval. Only the active approved plan may start Segment Matching; all other attempts are non-authoritative.
- The workspace projects invalid-plan recovery using the standard operational format: what happened, what completed work was preserved, what is blocked, recommended next action, and available actions.
- Available recovery actions are contextual and include Review Plan, Validate and Continue, Generate New Plan, View Diagnostics, or Abandon Attempt. Actions that cannot safely run are omitted or explain their prerequisite.
- Prompt reinforcement should state the sentence-span contract, required exception semantics, and output schema close to the output instruction, but prompt changes are defense in depth rather than the reliability mechanism.
- The synchronous-to-asynchronous bridge owns the event loop it creates. Before closing it, the bridge closes provider iterators where supported, shuts down asynchronous generators, cancels remaining loop-owned tasks, awaits cancellation, and restores the prior loop state.
- Stream consumers close provider streams or iterators in a `finally` path for success, timeout, cancellation, provider error, parse failure after completion, and downstream validation failure.
- A secondary cleanup error is recorded as bounded diagnostic data. It does not discard a successfully received response or replace the primary failure classification.
- The implementation must not promise that an external LLM will always return valid output. The product guarantee is that nonconforming output produces no lost completed result, unhandled validation exception, unsafe downstream progression, uncontrolled retry, or unresolved async resource warning.

## Testing Decisions

- The primary test seam is the public script-planning workflow from provider response through attempt persistence, validation, bounded repair, and creator-facing result. Tests assert externally observable state and calls, not private helper arrangement or exact prompt wording.
- Reuse the existing planning-workflow tests that already prove one continuity repair before Plan Approval. Extend this prior art to structural findings and invalid repair outcomes.
- Add a regression in which the provider returns a parsed plan containing a 9-sentence segment without `exception_reason`. Assert that the original attempt is persisted, one structured finding is produced, exactly one targeted repair occurs, the repaired plan is revalidated, and raw `ValueError` does not escape.
- Add a valid-plan control proving no repair request occurs and the plan reaches Plan Approval through the unchanged path.
- Add table-driven cases for malformed JSON, missing segments, invalid indexes, narration gaps, narration overlaps, below-range and above-range spans without a reason, invalid source windows, and mixed structural/continuity findings.
- Test malformed JSON through one format-only repair. If repair also fails, assert a durable waiting-for-review result, two linked attempts, preserved diagnostics, and no automatic third request.
- Test a parsed plan whose targeted repair remains invalid. Assert that matching cannot start, the repaired attempt remains inspectable, and creator recovery actions are projected.
- Test safe creator edits through the public workflow. Assert that an edit cannot reach Plan Approval until all structural and continuity checks pass.
- Test that retries create linked attempts with independent budgets and never overwrite prior attempts or invalidate unrelated evidence and narration artifacts.
- Test stale attempt completion against a changed input fingerprint. Assert that it remains inspectable but cannot replace the active plan.
- Test project refresh and application restart using durable attempt and checkpoint state rather than prior browser-session state.
- Keep provider-stream lifecycle tests at the provider boundary because stream closure is not fully observable through a successful planning result.
- Add controlled stream tests for success, no-first-chunk timeout, post-progress inactivity, total-budget expiry, provider error, and cancellation. Assert explicit close where supported and preservation of primary classification.
- Add a subprocess-level async bridge regression with a deliberately unfinished asynchronous generator. Assert that process output contains neither `Task was destroyed but it is pending!` nor an unclosed-stream warning.
- Add a secondary-cleanup-failure test proving a completed response remains a completed Fusion Plan Attempt while cleanup diagnostics are recorded separately.
- Acceptance requires the original incident fixture to reach either Plan Approval after one repair or a creator-recoverable checkpoint. It must never end at a generic script-generation error screen.

## Out of Scope

- Guaranteeing that any external LLM always emits valid JSON or follows every planning constraint.
- Replacing deterministic validation with prompt wording, provider-specific structured-output claims, or model self-assessment.
- Silently accepting an invalid plan, weakening the 3–8 sentence policy, or inventing an `exception_reason`.
- Automatically rewriting approved narration to make a plan valid.
- Automatically restarting narration generation, visual analysis, or the full-film workflow after a plan failure.
- Allowing an invalid, unapproved, stale, or abandoned attempt into Segment Matching, Finalization, Render Preflight, or rendering.
- Exposing full prompts, credentials, model chain-of-thought, unrestricted raw responses, or Python stack traces in the normal creator UI.
- Redesigning Narrative Map generation, Segment Matching quality, Finalization, TTS, subtitles, rendering, or the broader project UI beyond the recovery states needed by this gate.
- Adding provider-specific repair behavior that bypasses the shared planning workflow.

## Further Notes

- The confirmed incident demonstrates two independent defects: validator ordering prevented recovery from a nonconforming completed plan, while incomplete async cleanup generated a pending-task warning. Both are P0 because they occur on the same expensive creator journey, but their tests and failure classifications remain separate.
- LLM workload is a probability multiplier, not a sufficient diagnosis. Long context, 17,241-character output, numerous evidence constraints, recency loss within a prompt, sentence-tokenization differences, and competing format/content objectives can all increase nonconformance. The specification therefore combines concise prompt reinforcement with deterministic recovery and gating.
- The normal 3–8 narration-sentence range and explicit narrative-boundary exception retain their existing meaning. This work changes recovery behavior, not the planning policy.
- The canonical terms Fusion Plan Attempt and Plan Validation Finding are defined in the project glossary. The bounded-repair and authority decision is recorded in the Recoverable Fusion Plan Attempts architecture decision.
- This specification is the implementation source of truth for the P0 Script Planning Reliability Gate. The broader reliability and project-workspace specifications reference it and remain authoritative for their other phases.
