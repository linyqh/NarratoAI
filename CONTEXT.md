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

**Evidence Conflict**:
A validated record of a time window in which Subtitle Evidence and Visual Evidence cannot safely support the same narration claim; it carries source identity, both evidence statements, severity, and review status.
_Avoid_: model disagreement, mismatch

**Finalization Report**:
An audit of a Fusion Script's Original Sound Ratio, Highlight Candidate decisions, distribution, and unresolved Evidence Conflicts before rendering.
_Avoid_: render report, model explanation
