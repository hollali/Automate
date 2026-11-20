import unittest
from unittest.mock import MagicMock, patch

import Automate

FAKE_HTML = b"""
<html><body><table>
<tr><td class="title" valign=""><a href="item?id=1">A &amp; B &lt;tag&gt; caf\xc3\xa9</a></td></tr>
<tr><td class="title" valign=""><a href="https://example.com/x?a=1&amp;b=2">Second &amp; story</a></td></tr>
<tr><td class="title" valign=""><a href="?p=2">More</a></td></tr>
</table></body></html>
"""

EXPECTED_STORIES = [
    ("A & B <tag> café", "https://news.ycombinator.com/item?id=1"),
    ("Second & story", "https://example.com/x?a=1&b=2"),
]

CREDENTIALS = {
    "EMAIL_FROM": "from@example.com",
    "EMAIL_TO": "a@example.com",
    "EMAIL_PASSWORD": "app-password",
}


def fake_response():
    response = MagicMock()
    response.content = FAKE_HTML
    return response


class ExtractStoriesTests(unittest.TestCase):
    def test_extracts_titles_and_links(self):
        with patch.object(
            Automate.requests, "get", return_value=fake_response()
        ) as get:
            stories = Automate.extract_stories()
        self.assertEqual(stories, EXPECTED_STORIES)
        kwargs = get.call_args.kwargs
        self.assertEqual(kwargs["timeout"], Automate.REQUEST_TIMEOUT)
        self.assertIn("User-Agent", kwargs["headers"])

    def test_retries_http_errors_then_raises(self):
        with (
            patch.object(
                Automate.requests,
                "get",
                side_effect=Automate.requests.ConnectionError("offline"),
            ) as get,
            patch.object(Automate.time, "sleep"),
            self.assertRaises(Automate.requests.ConnectionError),
        ):
            Automate.extract_stories()
        self.assertEqual(get.call_count, Automate.RETRIES)


class BuildContentTests(unittest.TestCase):
    def test_escapes_and_numbers_without_gaps(self):
        content = Automate.build_content(EXPECTED_STORIES)
        self.assertIn(
            '1:: <a href="https://news.ycombinator.com/item?id=1">'
            "A &amp; B &lt;tag&gt; café</a>",
            content,
        )
        self.assertIn(
            '2:: <a href="https://example.com/x?a=1&amp;b=2">Second &amp; story</a>',
            content,
        )
        self.assertNotIn("More", content)
        self.assertNotIn("3::", content)

    def test_handles_story_without_link(self):
        content = Automate.build_content([("Plain <title>", "")])
        self.assertIn("1:: Plain &lt;title&gt;", content)


class BuildMessageTests(unittest.TestCase):
    def setUp(self):
        self.message = Automate.build_message(
            Automate.build_content(EXPECTED_STORIES),
            "from@example.com",
            ["a@example.com", "b@example.com"],
        )

    def test_headers(self):
        self.assertEqual(self.message["From"], "from@example.com")
        self.assertEqual(self.message["To"], "a@example.com, b@example.com")
        self.assertIn("Automated Email", self.message["Subject"])

    def test_body_is_utf8(self):
        part = self.message.get_payload()[0]
        self.assertEqual(part.get_content_charset(), "utf-8")
        self.assertIn("café", part.get_payload(decode=True).decode("utf-8"))


class SendEmailTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "server": "smtp.example.com",
            "port": 587,
            "sender": "from@example.com",
            "recipients": ["a@example.com", "b@example.com"],
            "password": "app-password",
        }
        patcher = patch.object(Automate.smtplib, "SMTP")
        self.smtp_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.server = self.smtp_cls.return_value.__enter__.return_value

    def test_delivery_sequence(self):
        Automate.send_email(self.config, "<b>stories</b>")
        self.smtp_cls.assert_called_once_with(
            "smtp.example.com", 587, timeout=Automate.SMTP_TIMEOUT
        )
        self.server.ehlo.assert_called()
        self.server.starttls.assert_called_once_with()
        self.server.login.assert_called_once_with("from@example.com", "app-password")
        self.assertEqual(
            self.server.sendmail.call_args.args[:2],
            ("from@example.com", ["a@example.com", "b@example.com"]),
        )

    def test_no_login_without_password(self):
        Automate.send_email(dict(self.config, password=""), "<b>stories</b>")
        self.server.login.assert_not_called()

    def test_debug_logging_never_enabled(self):
        Automate.send_email(self.config, "<b>stories</b>")
        self.server.set_debuglevel.assert_not_called()


class RetryTests(unittest.TestCase):
    def test_retries_until_success(self):
        calls = []

        def operation():
            calls.append(1)
            if len(calls) < 3:
                raise OSError("temporary")
            return "ok"

        with patch.object(Automate.time, "sleep") as sleep:
            self.assertEqual(Automate.retry(operation, exceptions=(OSError,)), "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_after_max_attempts(self):
        def operation():
            raise OSError("permanent")

        with patch.object(Automate.time, "sleep"), self.assertRaises(OSError):
            Automate.retry(operation, exceptions=(OSError,), attempts=2)


class ConfigTests(unittest.TestCase):
    def test_loads_environment(self):
        env = dict(
            CREDENTIALS,
            SMTP_SERVER="smtp.example.com",
            SMTP_PORT="2525",
            EMAIL_TO="a@example.com, b@example.com",
        )
        with patch.dict(Automate.os.environ, env, clear=True):
            config = Automate.load_config()
        self.assertEqual(
            config,
            {
                "server": "smtp.example.com",
                "port": 2525,
                "sender": "from@example.com",
                "recipients": ["a@example.com", "b@example.com"],
                "password": "app-password",
            },
        )

    def test_main_requires_credentials(self):
        with patch.dict(Automate.os.environ, {}, clear=True):
            self.assertEqual(Automate.main(), 1)

    def test_main_rejects_invalid_port(self):
        with patch.dict(Automate.os.environ, {"SMTP_PORT": "nope"}, clear=True):
            self.assertEqual(Automate.main(), 1)

    def test_main_skips_email_when_no_stories(self):
        with (
            patch.dict(Automate.os.environ, CREDENTIALS, clear=True),
            patch.object(Automate, "extract_stories", return_value=[]),
            patch.object(Automate, "send_email") as send,
        ):
            self.assertEqual(Automate.main(), 1)
        send.assert_not_called()

    def test_main_sends_email(self):
        with (
            patch.dict(Automate.os.environ, CREDENTIALS, clear=True),
            patch.object(Automate, "extract_stories", return_value=EXPECTED_STORIES),
            patch.object(Automate, "send_email") as send,
        ):
            self.assertEqual(Automate.main(), 0)
        send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
