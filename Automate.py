#!/usr/bin/env python3
"""Scrape Hacker News top stories and email them as an HTML message."""

import datetime as dt
import html
import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HN_URL = "https://news.ycombinator.com"
USER_AGENT = "Mozilla/5.0 (compatible; HNEmailer/1.0)"
REQUEST_TIMEOUT = 10
SMTP_TIMEOUT = 10
RETRIES = 3
RETRY_DELAY = 2


def load_config():
    """Read mail settings from the environment."""
    return {
        "server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "sender": os.getenv("EMAIL_FROM", ""),
        "recipients": [
            address.strip()
            for address in os.getenv("EMAIL_TO", "").split(",")
            if address.strip()
        ],
        "password": os.getenv("EMAIL_PASSWORD", ""),
    }


def retry(operation, exceptions=(Exception,), attempts=RETRIES, delay=RETRY_DELAY):
    """Run an operation, retrying only the given exception types."""
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except exceptions as exc:
            if attempt == attempts:
                raise
            print(
                f"Attempt {attempt}/{attempts} failed ({exc}); retrying in {delay}s...",
                file=sys.stderr,
            )
            time.sleep(delay)


def extract_stories(url=HN_URL):
    """Return (title, link) pairs for the stories on the HN front page."""
    print("Extracting stories...")

    def fetch():
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response.content

    soup = BeautifulSoup(
        retry(fetch, exceptions=(requests.RequestException,)), "html.parser"
    )
    stories = []
    for tag in soup.find_all("td", class_="title", valign=""):
        title = tag.get_text(strip=True)
        if not title or title == "More":
            continue
        link = tag.find("a")
        href = link.get("href", "") if link else ""
        stories.append((title, urljoin(url, href) if href else ""))
    return stories


def build_content(stories):
    """Render the story list as a polished, responsive HTML email body."""
    today = dt.datetime.now(dt.UTC).date()
    date_label = f"{today:%A, %B} {today.day}, {today.year}"

    rows = []
    for rank, (title, link) in enumerate(stories, start=1):
        safe_title = html.escape(title)
        if link:
            safe_link = html.escape(link, quote=True)
            item = f'{rank}:: <a href="{safe_link}">{safe_title}</a>'
        else:
            item = f"{rank}:: {safe_title}"
        rows.append(
            '<tr><td class="pad" style="padding:15px 32px;'
            "border-top:1px solid #eef1f4;font-size:15px;"
            'line-height:1.55;color:#1f2937;">'
            f"{item}</td></tr>"
        )

    style = (
        '<style type="text/css">'
        "a{color:#d9480f;text-decoration:none;font-weight:600;}"
        "a:hover{text-decoration:underline;}"
        "@media only screen and (max-width:620px){"
        "table.card{width:100%!important;border-radius:0!important;}"
        "td.pad{padding-left:20px!important;padding-right:20px!important;}"
        "}"
        "</style>"
    )

    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            ('<meta name="viewport" content="width=device-width,initial-scale=1">'),
            f"<title>HN Digest - {date_label}</title>",
            style,
            "</head>",
            '<body style="margin:0;padding:0;background:#f3f4f6;">',
            (
                '<table role="presentation" width="100%" cellpadding="0" '
                'cellspacing="0" border="0" '
                'style="background:#f3f4f6;padding:32px 16px;">'
            ),
            '<tr><td align="center">',
            (
                '<table role="presentation" class="card" width="600" '
                'cellpadding="0" cellspacing="0" border="0" '
                'style="width:600px;max-width:600px;background:#ffffff;'
                "border-radius:14px;overflow:hidden;"
                "box-shadow:0 6px 24px rgba(15,23,42,.08);"
                "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',"
                'Roboto,Helvetica,Arial,sans-serif;">'
            ),
            '<tr><td style="background:#ff6600;padding:30px 32px;">',
            (
                '<p style="margin:0;font-size:11px;font-weight:700;'
                "letter-spacing:2px;text-transform:uppercase;"
                'color:#ffd9c2;">Daily Digest</p>'
            ),
            (
                '<h1 style="margin:8px 0 0;font-size:26px;line-height:1.2;'
                'color:#ffffff;">Hacker News Top Stories</h1>'
            ),
            (
                f'<p style="margin:10px 0 0;font-size:14px;color:#ffe8d9;">'
                f"{date_label}</p>"
            ),
            "</td></tr>",
            '<tr><td class="pad" style="padding:28px 32px 24px;">',
            (
                '<p style="margin:0;font-size:15px;line-height:1.6;'
                'color:#4b5563;">Your daily roundup of the most-discussed '
                "stories from the Hacker News front page.</p>"
            ),
            "</td></tr>",
            '<tr><td class="pad" style="padding:0 32px 12px;">',
            (
                '<p style="margin:0;font-size:11px;font-weight:700;'
                "letter-spacing:1.6px;text-transform:uppercase;"
                'color:#9ca3af;">Top stories '
                f"&middot; {len(stories)}</p>"
            ),
            "</td></tr>",
            *rows,
            (
                '<tr><td class="pad" style="padding:24px 32px;'
                'border-top:1px solid #e5e7eb;background:#f9fafb;">'
            ),
            (
                '<p style="margin:0;font-size:12px;line-height:1.5;'
                'color:#9ca3af;text-align:center;">Automatically generated '
                "from news.ycombinator.com</p>"
            ),
            "</td></tr>",
            "</table>",
            "</td></tr>",
            "</table>",
            "</body>",
            "</html>",
        ]
    )


def build_message(content, sender, recipients):
    """Create the MIME message with a UTF-8 encoded HTML body."""
    today = dt.datetime.now(dt.UTC).date().isoformat()
    message = MIMEMultipart()
    message["Subject"] = f"Top News Stories HN [Automated Email] {today}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(content, "html", "utf-8"))
    return message


def send_email(config, content):
    """Deliver the message over SMTP with STARTTLS."""
    message = build_message(content, config["sender"], config["recipients"])

    def deliver():
        with smtplib.SMTP(
            config["server"], config["port"], timeout=SMTP_TIMEOUT
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if config["password"]:
                server.login(config["sender"], config["password"])
            server.sendmail(config["sender"], config["recipients"], message.as_string())

    print("Initiating server...")
    retry(
        deliver,
        exceptions=(OSError, smtplib.SMTPServerDisconnected),
    )
    print("Email sent...")


def main():
    try:
        config = load_config()
    except ValueError:
        print("SMTP_PORT must be an integer", file=sys.stderr)
        return 1

    missing = [
        name
        for name, value in (
            ("EMAIL_FROM", config["sender"]),
            ("EMAIL_TO", config["recipients"]),
            ("EMAIL_PASSWORD", config["password"]),
        )
        if not value
    ]
    if missing:
        print(
            "Missing required environment variable(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    try:
        stories = extract_stories()
        if not stories:
            print("No stories found; email not sent.", file=sys.stderr)
            return 1
        send_email(config, build_content(stories))
    except (requests.RequestException, OSError, smtplib.SMTPException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
