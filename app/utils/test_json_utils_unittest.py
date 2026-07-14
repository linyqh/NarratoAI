import unittest

from app.utils.json_utils import parse_and_fix_json, parse_script_payload


class JsonUtilsTests(unittest.TestCase):
    def test_invalid_json_returns_none(self):
        self.assertIsNone(parse_and_fix_json("not a json response"))

    def test_extracts_json_code_block(self):
        parsed = parse_and_fix_json('result:\n```json\n{"items": []}\n```')
        self.assertEqual({"items": []}, parsed)

    def test_repairs_unquoted_keys_and_trailing_commas(self):
        parsed = parse_and_fix_json('{items: [{"timestamp": "00:00-00:05",}],}')
        self.assertEqual(
            {"items": [{"timestamp": "00:00-00:05"}]},
            parsed,
        )

    def test_parse_script_payload_accepts_items_wrapper(self):
        self.assertEqual([{"_id": 1}], parse_script_payload('{"items": [{"_id": 1}]}'))

    def test_parse_script_payload_rejects_invalid_shape(self):
        with self.assertRaises(ValueError):
            parse_script_payload('{"unexpected": []}')


if __name__ == "__main__":
    unittest.main()
