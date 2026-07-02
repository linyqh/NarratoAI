import unittest

from webui.tools.generate_short_summary import _format_progress_status, parse_and_fix_json


class GenerateShortSummaryJsonTests(unittest.TestCase):
    def test_progress_message_does_not_prefix_fake_percentage(self):
        status = _format_progress_status(60, "正在生成文案...")

        self.assertEqual("正在生成文案...", status)
        self.assertNotIn("60%", status)

    def test_invalid_json_does_not_create_default_fake_script(self):
        self.assertIsNone(parse_and_fix_json("not a json response"))

    def test_json_code_block_is_parsed(self):
        parsed = parse_and_fix_json(
            """```json
{"items": [{"_id": 1, "timestamp": "00:00:01,000-00:00:02,000"}]}
```"""
        )

        self.assertEqual(1, parsed["items"][0]["_id"])

    def test_repair_does_not_corrupt_timestamp_values(self):
        parsed = parse_and_fix_json(
            """```json
{
  items: [
    {_id: 1, timestamp: "00:00:01,000-00:00:02,000",},
  ],
}
```"""
        )

        self.assertEqual("00:00:01,000-00:00:02,000", parsed["items"][0]["timestamp"])


if __name__ == "__main__":
    unittest.main()
