import unittest

from app.services.fusion_preflight import build_render_preflight


class FusionRenderPreflightTests(unittest.TestCase):
    def test_high_conflict_and_failed_segment_block_rendering(self):
        preflight = build_render_preflight(
            continuity_report={"is_renderable": True, "findings": []},
            evidence_conflicts=[{"severity": "high", "status": "unresolved"}],
            segment_matches=[
                {"segment_id": "segment-1", "status": "succeeded"},
                {"segment_id": "segment-2", "status": "failed"},
            ],
        )

        self.assertFalse(preflight.can_render())
        self.assertEqual(
            {"unresolved_high_severity_conflict", "segment_match_failed"},
            {item.code for item in preflight.blockers},
        )

    def test_lower_risk_conflict_requires_a_recorded_override_reason(self):
        preflight = build_render_preflight(
            continuity_report={"is_renderable": True, "findings": []},
            evidence_conflicts=[{"severity": "medium", "status": "unresolved"}],
        )

        self.assertFalse(preflight.can_render())
        self.assertTrue(preflight.warnings)
        self.assertTrue(preflight.can_render("已核验并接受该创作取舍"))

    def test_passed_preflight_is_renderable_without_an_override(self):
        preflight = build_render_preflight(
            continuity_report={"is_renderable": True, "findings": []},
            evidence_conflicts=[],
        )

        self.assertTrue(preflight.can_render())
        self.assertEqual([], preflight.to_dict()["blockers"])


if __name__ == "__main__":
    unittest.main()
