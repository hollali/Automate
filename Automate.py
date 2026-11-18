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
                f"Attempt {attempt}/{attempts} failed ({exc}); "
                f"retrying in {delay}s...",
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
    """Render the story list as an HTML email body."""
    lines = ["<b>Top Stories:</b><br>", "-" * 50 + "<br>"]
    for rank, (title, link) in enumerate(stories, start=1):
        safe_title = html.escape(title)
        if link:
            safe_link = html.escape(link, quote=True)
            lines.append(f'{rank}:: <a href="{safe_link}">{safe_title}</a><br>')
        else:
            lines.append(f"{rank}:: {safe_title}<br>")
    lines.extend(["<br>-----<br>", "<br>End of Message"])
    return "\n".join(lines)


def build_message(content, sender, recipients):
    """Create the MIME message with a UTF-8 encoded HTML body."""
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
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
            server.sendmail(
                config["sender"], config["recipients"], message.as_string()
            )

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
