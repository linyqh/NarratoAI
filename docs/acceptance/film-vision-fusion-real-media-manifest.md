# Film Vision Fusion real-media acceptance manifest

Keep source media and provider logs outside version control. For every entry below, store only the local path, source identity, generated-artifact paths, and the completed scorecard in the team’s secure review location.

| Material class | Required finished samples | Required checks |
| --- | ---: | --- |
| Dialogue-heavy | 2 | Subtitle/visual claim fit, character clarity, TTS/subtitle/video sync |
| Visual/action-heavy | 2 | Picture/narration fit, cut continuity, OST placement/value |
| Multi-video or non-linear | 2 | Source identity, time-range transitions, Narrative Bridges, recovery/resume |

Score each finished sample from 1–5 for: opening attraction, character clarity, causal continuity, picture/narration fit, pacing, original-sound value, and ending completeness. No category may be below 3 and the mean must be at least 4.

Before acceptance, run:

```powershell
..\runtime\python\python.exe -m unittest app.services.test_film_vision_fusion_unittest app.services.test_fusion_script_finalizer_unittest app.services.test_fusion_script_pipeline_unittest app.services.test_fusion_matching_workflow_unittest app.services.test_fusion_preflight_unittest app.services.test_narrative_map_unittest app.services.test_fusion_workspace_unittest app.services.llm.test_openai_compat_unittest webui.tools.test_generate_short_summary_unittest
```
