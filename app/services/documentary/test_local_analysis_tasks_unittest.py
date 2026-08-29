import tempfile
import time
import unittest
from pathlib import Path

from app.services.documentary.local_analysis_tasks import LocalAnalysisTaskRunner, LocalAnalysisTaskStore, estimate_full_film_analysis


class FullFilmEstimateTests(unittest.TestCase):
    def test_estimate_uses_full_duration_and_batch_size(self):
        estimate = estimate_full_film_analysis(
            duration_seconds=7_200,
            frame_interval_seconds=6,
            vision_batch_size=8,
            max_concurrency=2,
        )

        self.assertEqual(1_200, estimate.keyframe_count)
        self.assertEqual(150, estimate.request_count)
        self.assertGreater(estimate.estimated_minutes, 0)

    def test_rejects_non_positive_analysis_settings(self):
        with self.assertRaises(ValueError):
            estimate_full_film_analysis(10, 0, 8, 2)

    def test_task_store_persists_progress_and_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalAnalysisTaskStore(Path(directory))
            task = store.create({"video_path": "film.mp4"}, {"sha256": "a" * 64})
            store.update(task["task_id"], status="running", completed_batches=[{"batch_index": 0}])
            store.request_cancel(task["task_id"])

            restored = store.read(task["task_id"])

        self.assertEqual("running", restored["status"])
        self.assertTrue(restored["cancel_requested"])
        self.assertEqual([{"batch_index": 0}], restored["completed_batches"])

    def test_background_runner_persists_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalAnalysisTaskStore(Path(directory))
            task = store.create({"video_path": "film.mp4"}, {"sha256": "a" * 64})
            runner = LocalAnalysisTaskRunner(store)
            thread = runner.start(task["task_id"], lambda progress, checkpoint, cancelled: {"artifact_path": "result.json"})
            thread.join(timeout=2)
            restored = store.read(task["task_id"])

        self.assertEqual("completed", restored["status"])
        self.assertEqual("result.json", restored["artifact_path"])


if __name__ == "__main__":
    unittest.main()
