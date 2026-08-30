# Recoverable Fusion Plan Attempts

Fusion Segment Plan generation is an expensive, provider-dependent operation. A completed response can be malformed or violate deterministic planning constraints without meaning that its usable diagnostic and recovery context should be discarded. NarratoAI will persist every completed response as a Fusion Plan Attempt before parsing, then convert deterministic rejection into structured Plan Validation Findings.

One attempt receives at most one targeted structural/continuity repair, or one format-only repair when parsing is impossible. We rejected silently adding an `exception_reason`, accepting invalid ranges, and automatically restarting the complete narration-generation workflow: each would hide an evidence or creator-control problem and can waste already completed work. A failed repair becomes a creator-recoverable Review Checkpoint; a manually edited plan still requires validation and Plan Approval.

The attempt record is append-only and linked across repair or creator retry. It is diagnostic evidence, never a valid plan. Matching, finalization, and rendering admit only an approved, validated Fusion Segment Plan. The planning bridge also owns explicit provider-stream and event-loop cleanup so a completed response does not leave unfinished asynchronous-generator warnings behind.
