import unittest

from app.services.short_drama_narration_validation import (
    build_subtitle_index,
    normalize_script_video_sources,
    validate_narration_script_items,
)


SUBTITLE_CONTENT = """# 视频 1: first.mp4
字幕文件: first.srt
1
00:00:01,000 --> 00:00:04,000
女主被众人误会。

2
00:00:04,000 --> 00:00:08,000
男主冷眼看着她。

# 视频 2: second.mp4
字幕文件: second.srt
1
00:00:02,000 --> 00:00:05,000
女主终于拿出证据。

2
00:00:05,000 --> 00:00:09,000
众人震惊，反派慌了。
"""


class ShortDramaNarrationValidationTests(unittest.TestCase):
    def setUp(self):
        self.video_paths = ["/tmp/first.mp4", "/tmp/second.mp4"]
        self.subtitle_index = build_subtitle_index(SUBTITLE_CONTENT, self.video_paths)

    def test_build_subtitle_index_preserves_multi_video_sources(self):
        self.assertEqual(4, len(self.subtitle_index))
        self.assertEqual({1, 2}, {cue.video_id for cue in self.subtitle_index})
        self.assertEqual("first.mp4", self.subtitle_index[0].video_name)
        self.assertEqual("second.mp4", self.subtitle_index[2].video_name)
        self.assertEqual("00:00:02,000-00:00:05,000", self.subtitle_index[2].timestamp)

    def test_valid_script_passes_and_normalizes_video_name(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "wrong-name.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "女主被误会",
                "narration": "她被当众误会。",
                "OST": 0,
            },
            {
                "_id": 2,
                "video_name": "second.mp4",
                "timestamp": "00:00:02,000-00:00:05,000",
                "picture": "女主拿出证据",
                "narration": "播放原片2",
                "OST": 1,
            },
        ]

        normalized = normalize_script_video_sources(items, self.video_paths)
        result = validate_narration_script_items(normalized, self.subtitle_index, self.video_paths)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(2, result.items[1]["video_id"])
        self.assertEqual("second.mp4", result.items[1]["video_name"])

    def test_invalid_timestamp_and_overlap_fail(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:01,000-00:00:05,000",
                "picture": "画面",
                "narration": "解说",
                "OST": 0,
            },
            {
                "_id": 2,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:04,500-00:00:08,000",
                "picture": "画面",
                "narration": "解说",
                "OST": 0,
            },
            {
                "_id": 3,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "bad",
                "picture": "画面",
                "narration": "解说",
                "OST": 0,
            },
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("重叠" in error for error in result.errors))
        self.assertTrue(any("时间戳格式" in error for error in result.errors))

    def test_invalid_video_id_does_not_default_to_first_video(self):
        items = [
            {
                "_id": 1,
                "video_id": 99,
                "video_name": "missing.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "画面",
                "narration": "解说",
                "OST": 0,
            }
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("video_id=99" in error for error in result.errors))

    def test_out_of_range_timestamp_fails(self):
        items = [
            {
                "_id": 1,
                "video_id": 2,
                "video_name": "second.mp4",
                "timestamp": "00:00:20,000-00:00:25,000",
                "picture": "画面",
                "narration": "解说",
                "OST": 0,
            }
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("不在视频 2 的字幕范围内" in error for error in result.errors))

    def test_three_consecutive_original_audio_segments_fail(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "女主被误会",
                "narration": "她被当众误会。",
                "OST": 0,
            },
            {
                "_id": 2,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:04,000-00:00:05,000",
                "picture": "男主看着她",
                "narration": "播放原片2",
                "OST": 1,
            },
            {
                "_id": 3,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:05,000-00:00:06,000",
                "picture": "男主看着她",
                "narration": "播放原片3",
                "OST": 1,
            },
            {
                "_id": 4,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:06,000-00:00:08,000",
                "picture": "男主继续观察",
                "narration": "播放原片4",
                "OST": 1,
            },
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("连续原声过多" in error for error in result.errors))

    def test_cross_video_original_audio_requires_narration_bridge(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "女主被误会",
                "narration": "她被当众误会。",
                "OST": 0,
            },
            {
                "_id": 2,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:04,000-00:00:08,000",
                "picture": "男主看着她",
                "narration": "播放原片2",
                "OST": 1,
            },
            {
                "_id": 3,
                "video_id": 2,
                "video_name": "second.mp4",
                "timestamp": "00:00:02,000-00:00:05,000",
                "picture": "女主拿出证据",
                "narration": "播放原片3",
                "OST": 1,
            },
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("跨视频切换缺少 OST=0 解说桥段" in error for error in result.errors))

    def test_cross_video_switch_with_narration_bridge_passes(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "女主被误会",
                "narration": "她被当众误会。",
                "OST": 0,
            },
            {
                "_id": 2,
                "video_id": 2,
                "video_name": "second.mp4",
                "timestamp": "00:00:02,000-00:00:05,000",
                "picture": "女主拿出证据",
                "narration": "播放原片2",
                "OST": 1,
            },
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertTrue(result.valid, result.errors)

    def test_first_segment_must_be_narration_hook(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "女主被误会",
                "narration": "播放原片1",
                "OST": 1,
            }
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("解说开场钩子" in error for error in result.errors))

    def test_dense_narration_fails_when_video_duration_is_too_short(self):
        items = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "first.mp4",
                "timestamp": "00:00:01,000-00:00:04,000",
                "picture": "女主被误会",
                "narration": "她明明什么都没做却被所有人推到风口浪尖只能独自承受委屈",
                "OST": 0,
            }
        ]

        result = validate_narration_script_items(items, self.subtitle_index, self.video_paths)

        self.assertFalse(result.valid)
        self.assertTrue(any("解说过密" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
