import subprocess
import unittest
from unittest import mock

from app.services import merger_video


class MergerVideoConcatTests(unittest.TestCase):
    def test_can_concat_video_copy_when_signatures_match(self):
        signature = {
            "codec_name": "h264",
            "profile": "High",
            "width": 1080,
            "height": 1920,
            "pix_fmt": "yuv420p",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "sample_aspect_ratio": "1:1",
        }

        with mock.patch.object(
            merger_video,
            "_get_video_stream_signature",
            side_effect=[signature, dict(signature)],
        ):
            self.assertTrue(merger_video._can_concat_video_copy(["1.mp4", "2.mp4"]))

    def test_can_concat_video_copy_rejects_mismatched_signature(self):
        base_signature = {
            "codec_name": "h264",
            "profile": "High",
            "width": 1080,
            "height": 1920,
            "pix_fmt": "yuv420p",
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "time_base": "1/15360",
            "sample_aspect_ratio": "1:1",
        }
        mismatch_signature = dict(base_signature, r_frame_rate="24000/1001")

        with mock.patch.object(
            merger_video,
            "_get_video_stream_signature",
            side_effect=[base_signature, mismatch_signature],
        ):
            self.assertFalse(merger_video._can_concat_video_copy(["1.mp4", "2.mp4"]))

    def test_concat_video_streams_prefers_copy_when_compatible(self):
        completed = subprocess.CompletedProcess(args=["ffmpeg"], returncode=0)

        with (
            mock.patch.object(merger_video, "_can_concat_video_copy", return_value=True),
            mock.patch.object(merger_video, "_concat_duration_matches", return_value=True),
            mock.patch.object(merger_video.subprocess, "run", return_value=completed) as run_mock,
        ):
            merger_video._concat_video_streams(
                ["1.mp4", "2.mp4"],
                "concat.txt",
                "video_concat.mp4",
                threads=4,
            )

        cmd = run_mock.call_args.args[0]
        self.assertEqual("copy", cmd[cmd.index("-c:v") + 1])
        self.assertNotIn("libx264", cmd)

    def test_concat_video_streams_falls_back_when_copy_duration_mismatches(self):
        completed = subprocess.CompletedProcess(args=["ffmpeg"], returncode=0)

        with (
            mock.patch.object(merger_video, "_can_concat_video_copy", return_value=True),
            mock.patch.object(merger_video, "_concat_duration_matches", return_value=False),
            mock.patch.object(merger_video.os.path, "exists", return_value=False),
            mock.patch.object(merger_video.subprocess, "run", return_value=completed) as run_mock,
        ):
            merger_video._concat_video_streams(
                ["1.mp4", "2.mp4"],
                "concat.txt",
                "video_concat.mp4",
                threads=6,
            )

        self.assertEqual(2, run_mock.call_count)
        fallback_cmd = run_mock.call_args_list[1].args[0]
        self.assertEqual("libx264", fallback_cmd[fallback_cmd.index("-c:v") + 1])
        self.assertEqual("6", fallback_cmd[fallback_cmd.index("-threads") + 1])

    def test_concat_video_streams_falls_back_to_reencode_when_copy_fails(self):
        copy_error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ffmpeg"],
            stderr=b"copy failed",
        )
        completed = subprocess.CompletedProcess(args=["ffmpeg"], returncode=0)

        with (
            mock.patch.object(merger_video, "_can_concat_video_copy", return_value=True),
            mock.patch.object(
                merger_video.subprocess,
                "run",
                side_effect=[copy_error, completed],
            ) as run_mock,
        ):
            merger_video._concat_video_streams(
                ["1.mp4", "2.mp4"],
                "concat.txt",
                "video_concat.mp4",
                threads=8,
            )

        self.assertEqual(2, run_mock.call_count)
        fallback_cmd = run_mock.call_args_list[1].args[0]
        self.assertEqual("libx264", fallback_cmd[fallback_cmd.index("-c:v") + 1])
        self.assertEqual("8", fallback_cmd[fallback_cmd.index("-threads") + 1])


if __name__ == "__main__":
    unittest.main()
