import unittest

from webui.tools.generate_script_short import _parse_generated_script_payload


class GenerateScriptShortPayloadTests(unittest.TestCase):
    def test_parse_generated_script_payload_keeps_list_payload(self):
        payload = [{"_id": 1, "timestamp": "00:00:01,000-00:00:02,000"}]

        self.assertEqual(payload, _parse_generated_script_payload(payload))

    def test_parse_generated_script_payload_accepts_items_wrapper(self):
        payload = '{"items": [{"_id": 1, "timestamp": "00:00:01,000-00:00:02,000"}]}'

        parsed = _parse_generated_script_payload(payload)

        self.assertEqual(1, parsed[0]["_id"])

    def test_parse_generated_script_payload_repairs_common_llm_json_formatting(self):
        payload = """```json
{
  "items": [
    {"_id": 1, "timestamp": "00:00:01,000-00:00:02,000",},
  ],
}
```"""

        parsed = _parse_generated_script_payload(payload)

        self.assertEqual(1, parsed[0]["_id"])

    def test_parse_generated_script_payload_rejects_invalid_shape(self):
        with self.assertRaises(ValueError):
            _parse_generated_script_payload('{"unexpected": []}')


if __name__ == "__main__":
    unittest.main()
