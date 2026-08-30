import unittest

from app.services.narrative_map import build_narrative_map, evaluate_narrative_quality, review_narrative_map


class NarrativeMapTests(unittest.TestCase):
    def _plan(self):
        return {"segments": [
            {"segment_id": "segment-1", "sentence_start": 1, "sentence_end": 1, "core_window": "00:00:00,000-00:00:10,000", "active_subject": "甲", "entering_state": "受压", "trigger_event": "事件", "exiting_state": "选择", "bridge_to_next": False},
            {"segment_id": "segment-2", "sentence_start": 2, "sentence_end": 2, "core_window": "00:00:10,000-00:00:20,000", "active_subject": "乙", "entering_state": "受压", "trigger_event": "", "exiting_state": "", "bridge_to_next": False},
        ]}

    def test_map_is_evidence_bounded_and_does_not_invent_fields(self):
        artifact = build_narrative_map(approved_narration="第一句。第二句。", plan_payload=self._plan(), subtitle_evidence="字幕证据", visual_evidence="")

        self.assertEqual("Narrative Map", artifact["artifact_type"])
        self.assertEqual("甲", artifact["beats"][0]["active_subject"])
        self.assertEqual("pending", artifact["approval_status"])

    def test_quality_suggestions_identify_causal_and_subject_handoffs(self):
        artifact = build_narrative_map(approved_narration="第一句。第二句。", plan_payload=self._plan(), subtitle_evidence="字幕证据", visual_evidence="")
        findings = evaluate_narrative_quality(artifact, [])

        self.assertEqual({"missing_causal_bridge", "unstable_subject_handoff"}, {finding["code"] for finding in findings})

    def test_creator_edit_reports_only_affected_segment_invalidation(self):
        artifact = build_narrative_map(approved_narration="第一句。第二句。", plan_payload=self._plan(), subtitle_evidence="字幕证据", visual_evidence="")
        edited = [dict(beat) for beat in artifact["beats"]]
        edited[1]["next_risk_or_choice"] = "新的风险"

        reviewed, impact = review_narrative_map(artifact, action="applied_draft", edited_beats=edited)

        self.assertEqual("applied_draft", reviewed["approval_status"])
        self.assertEqual(["segment-2"], impact["invalidates_segment_matches"])
        self.assertTrue(impact["retains_visual_evidence"])

    def test_creator_cannot_expand_a_story_beat_evidence_window(self):
        artifact = build_narrative_map(approved_narration="第一句。第二句。", plan_payload=self._plan(), subtitle_evidence="字幕证据", visual_evidence="")
        edited = [dict(beat) for beat in artifact["beats"]]
        edited[0]["evidence_window"] = "00:00:00,000-00:00:30,000"

        with self.assertRaisesRegex(ValueError, "cannot expand"):
            review_narrative_map(artifact, action="applied_draft", edited_beats=edited)

    def test_quality_suggestions_cover_temporal_jump_density_and_unlinked_highlight(self):
        artifact = build_narrative_map(approved_narration="第一句。第二句。", plan_payload={"segments": [
            {**self._plan()["segments"][0], "core_window": "00:00:00,000-00:00:10,000"},
            {**self._plan()["segments"][1], "core_window": "00:03:00,000-00:03:10,000"},
        ]}, subtitle_evidence="字幕证据", visual_evidence="")
        findings = evaluate_narrative_quality(artifact, [
            {"timestamp": "00:00:00,000-00:00:01,000", "narration": "这是一段很长很长很长很长很长很长的解说", "OST": 0},
            {"timestamp": "00:00:01,000-00:00:02,000", "narration": "原片", "OST": 1},
        ])

        self.assertTrue({"unexplained_temporal_jump", "narration_density_high", "highlight_story_relevance_unknown"}.issubset({item["code"] for item in findings}))

    def test_quality_suggestion_flags_pronouns_without_a_story_beat_subject(self):
        artifact = build_narrative_map(
            approved_narration="他立刻离开。",
            plan_payload={"segments": [{
                **self._plan()["segments"][0],
                "active_subject": "",
            }]},
            subtitle_evidence="字幕证据",
            visual_evidence="",
        )

        findings = evaluate_narrative_quality(
            artifact,
            [{
                "_segment_id": "segment-1",
                "timestamp": "00:00:00,000-00:00:10,000",
                "narration": "他立刻离开。",
                "OST": 0,
            }],
        )

        self.assertIn("ambiguous_character_reference", {item["code"] for item in findings})


if __name__ == "__main__":
    unittest.main()
