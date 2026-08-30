# Film Vision Fusion real-media acceptance manifest

Keep source media and provider logs outside version control. For every entry below, store only the local path, source identity, generated-artifact paths, and the completed scorecard in the team’s secure review location.

| Material class | Required finished samples | Required checks |
| --- | ---: | --- |
| Dialogue-heavy | 2 | Subtitle/visual claim fit, character clarity, TTS/subtitle/video sync |
| Visual/action-heavy | 2 | Picture/narration fit, cut continuity, OST placement/value |
| Multi-video or non-linear | 2 | Source identity, time-range transitions, Narrative Bridges, recovery/resume |

Score each finished sample from 1–5 for: opening attraction, character clarity, causal continuity, picture/narration fit, pacing, original-sound value, and ending completeness. No category may be below 3 and the mean must be at least 4.

## Per-sample record

Complete one redacted record for each of the six samples in the secure review
location. Do not commit source media, rendered video, raw prompts, provider
responses, API keys, or any other sensitive request content.

```text
Sample ID:
Material class: dialogue-heavy | visual/action-heavy | multi-video/non-linear
Source identity/hash:
Subtitle identity/hash:
Provider/model and prompt version:

Visual Evidence artifact path:
Narrative Map path:
Fusion Segment Plan path:
Segment Match path:
Finalized Script path:
Evidence Conflicts path:
Render Preflight path:
TTS timing diagnostics path:
SRT path:
Rendered-video path:

Generation duration:
Timeout / retry / repair events:
Hard gates passed: yes | no

Opening attraction (1-5):
Character clarity (1-5):
Causal continuity (1-5):
Picture/narration fit (1-5):
Pacing (1-5):
Original-sound value (1-5):
Ending completeness (1-5):
Mean:
Would publish: yes | yes-after-minor-edits | no
Reviewer notes:
```

## Timestamped observation log

Record each observed viewing problem or success at a source/output range so it
can be traced back to the Finalized Segment, Segment Match, Story Beat, and
the relevant Subtitle or Visual Evidence.

| Output range | Observation | Severity | Trace target | Suggested next check |
| --- | --- | --- | --- | --- |
| `00:02:13-00:02:25` | Example: character reference becomes ambiguous | high | Finalized Segment → Story Beat | active subject / handoff |
| `00:03:42-00:03:51` | Example: narration repeats an obvious picture | medium | Segment Match → Visual Evidence | picture/narration fit |
| `00:05:17-00:05:26` | Example: OST highlight adds performance value | positive | Highlight Candidate → Finalizer | preserve selection |

Before acceptance, run:

```powershell
..\runtime\python\python.exe -m unittest app.services.test_film_vision_fusion_unittest app.services.test_fusion_script_finalizer_unittest app.services.test_fusion_script_pipeline_unittest app.services.test_fusion_matching_workflow_unittest app.services.test_fusion_preflight_unittest app.services.test_narrative_map_unittest app.services.test_fusion_workspace_unittest app.services.llm.test_openai_compat_unittest webui.tools.test_generate_short_summary_unittest
```
