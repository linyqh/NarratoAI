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


class PlotSearchWiringTests(unittest.TestCase):
    def test_online_opt_out_never_calls_search(self):
        from unittest.mock import patch
        from webui.tools import generate_short_summary as summary
        with patch.object(summary, 'search_story_context') as search:
            self.assertEqual('Subtitles', summary._build_plot_analysis_input('Subtitles', enable_web_search=False))
        search.assert_not_called()

    def test_saved_provider_and_keywords_reach_both_plot_workflows(self):
        from unittest.mock import patch
        from webui.tools import generate_short_summary as summary
        for keywords in [summary.SHORT_DRAMA_SEARCH_KEYWORDS, summary.FILM_TV_SEARCH_KEYWORDS]:
            with patch.dict(summary.config.app, {'web_search_provider': 'parallel', 'tavily_api_key': 'saved'}), patch.object(summary.st, 'session_state', {}), patch.object(summary, 'search_story_context') as search:
                search.return_value = {'provider': 'parallel', 'query': 'Title', 'results': []}
                text = summary._build_plot_analysis_input('Subtitles', short_name='Title', enable_web_search=True, search_keywords=keywords)
                self.assertIn('# Parallel 联网检索结果', text)
                self.assertNotIn('Tavily', text)
                self.assertIn('Subtitles', text)
                self.assertEqual('parallel', search.call_args.kwargs['provider'])
                self.assertEqual(keywords, search.call_args.kwargs['search_keywords'])
                self.assertEqual('saved', search.call_args.args[1])

    def test_disabled_and_explicit_missing_tavily_block_without_network(self):
        import os
        from unittest.mock import patch
        from webui.tools import generate_short_summary as summary
        for provider in ['disabled', 'tavily']:
            with patch.dict(summary.config.app, {'web_search_provider': provider, 'tavily_api_key': ''}), patch.dict(os.environ, {'TAVILY_API_KEY': ''}), patch.object(summary.st, 'session_state', {}), patch.object(summary.st, 'error') as error, patch('requests.sessions.Session.request') as network:
                self.assertIsNone(summary._build_plot_analysis_input('Subtitles', short_name='Title', enable_web_search=True))
                network.assert_not_called()
                error.assert_called_once()

    def test_provider_widget_persists_selection(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        from app.config import config
        translations = json.loads(Path('webui/i18n/en.json').read_text())['Translation']
        script = '''
import json
from pathlib import Path
from webui.components.basic_settings import render_tavily_search_settings
translations = json.loads(Path('webui/i18n/en.json').read_text())['Translation']
render_tavily_search_settings(lambda key: translations.get(key, key))
'''
        with patch.dict(config.app, {'web_search_provider': 'auto', 'tavily_api_key': ''}), patch.object(config, 'save_config') as save:
            app = AppTest.from_string(script).run()
            self.assertEqual(0, len(app.exception))
            app.selectbox[0].select('parallel').run()
            self.assertEqual(0, len(app.exception))
            self.assertEqual('parallel', config.app['web_search_provider'])
            save.assert_called_once()
            self.assertIn(translations['Search provider parallel'], app.selectbox[0].options)


if __name__ == "__main__":
    unittest.main()
