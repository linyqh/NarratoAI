import unittest

from app.services.narrative_map import build_narrative_map, evaluate_narrative_quality


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


if __name__ == "__main__":
    unittest.main()
