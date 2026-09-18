import unittest
from unittest.mock import patch

from crawler import Crawler


class Response:
    status_code = 200
    text = """User-agent: llms-txt-gen-test
Disallow: /private

User-agent: *
Allow: /
"""


class CustomUserAgentTests(unittest.TestCase):
    def test_custom_user_agent_controls_robots_decisions(self):
        crawler = Crawler(
            "https://example.com",
            delay=0,
            user_agent="llms-txt-gen-test",
        )
        with patch("crawler._get", return_value=Response()):
            crawler.load_robots()

        self.assertFalse(crawler._allowed("https://example.com/private/catalog"))
        self.assertTrue(crawler._allowed("https://example.com/public/catalog"))
        self.assertEqual(crawler.result.skipped_by_robots, 1)

    def test_custom_user_agent_is_sent_on_http_requests(self):
        crawler = Crawler(
            "https://example.com",
            user_agent="llms-txt-gen-test",
        )
        self.assertEqual(crawler.session.headers["User-Agent"], "llms-txt-gen-test")
        self.assertEqual(crawler.user_agent, "llms-txt-gen-test")


if __name__ == "__main__":
    unittest.main()
