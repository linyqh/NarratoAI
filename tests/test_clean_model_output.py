import unittest

from app.utils.utils import clean_model_output


class CleanModelOutputTests(unittest.TestCase):
    def test_removes_markdown_code_fence(self):
        raw_output = """```json\n{\"message\": \"hello\"}\n```"""
        self.assertEqual(clean_model_output(raw_output), '{"message": "hello"}')

    def test_preserves_content_without_code_fence(self):
        raw_output = '{"message": "json`` value"}'
        self.assertEqual(clean_model_output(raw_output), raw_output)

    def test_handles_non_string_input(self):
        payload = {"message": "hello"}
        self.assertIs(clean_model_output(payload), payload)

    def test_case_insensitive_language_hint(self):
        raw_output = """```JSON\n{\"message\": \"hello\"}\n```"""
        self.assertEqual(clean_model_output(raw_output), '{"message": "hello"}')


if __name__ == "__main__":
    unittest.main()
