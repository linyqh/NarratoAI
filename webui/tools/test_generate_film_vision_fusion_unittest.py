import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webui.tools.generate_film_vision_fusion import list_local_visual_evidence_artifacts


class LocalVisualArtifactListingTests(unittest.TestCase):
    def test_lists_only_valid_visual_artifacts_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis = root / "temp" / "analysis"
            analysis.mkdir(parents=True)
            older = analysis / "frame_analysis_20260101_000000.json"
            newer = analysis / "frame_analysis_20260102_000000.json"
            older.write_text(json.dumps({"artifact_version": 1}), encoding="utf-8")
            newer.write_text(json.dumps({"artifact_version": 1}), encoding="utf-8")
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))
            (analysis / "frame_analysis_invalid.json").write_text("not json", encoding="utf-8")
            (analysis / "unrelated.json").write_text(json.dumps({"artifact_version": 1}), encoding="utf-8")

            with patch("webui.tools.generate_film_vision_fusion.utils.storage_dir", return_value=str(root)):
                artifacts = list_local_visual_evidence_artifacts()

        self.assertEqual([newer.name, older.name], [item.name for item in artifacts])


if __name__ == "__main__":
    unittest.main()
