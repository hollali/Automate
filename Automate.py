#!/usr/bin/env python3
"""Scrape Hacker News top stories and email them as an HTML message."""

import argparse
import datetime as dt
import html
import os
import smtplib
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HN_URL = "https://news.ycombinator.com"
USER_AGENT = "Mozilla/5.0 (compatible; HNEmailer/1.0)"
REQUEST_TIMEOUT = 10
SMTP_TIMEOUT = 10
RETRIES = 3
RETRY_DELAY = 2
MAX_STORIES = 40
SENT_DB_DEFAULT = "sent_stories.sqlite3"

DEFAULT_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://www.technologyreview.com/feed/",
    "https://www.zdnet.com/news/rss.xml",
    "https://www.cnet.com/rss/all/",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
]


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
    for tag in soup.find_all("td", class_="title"):
        titleline = tag.find("span", class_="titleline")
        if titleline is not None:
            link = titleline.find("a")
            title = link.get_text(strip=True) if link is not None else titleline.get_text(strip=True)
        else:
            link = tag.find("a")
            title = link.get_text(strip=True) if link is not None else tag.get_text(strip=True)
        if not title or title == "More":
            continue
        if link is None or "morelink" in (link.get("class") or []):
            continue
        href = link.get("href", "")
        stories.append((title, urljoin(url, href) if href else ""))
    return stories

def _text(element, path):
    """Return stripped text for the first matching sub-element."""
    found = element.find(path)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def extract_feed_stories(url, limit=8):
    """Return (title, link) pairs parsed from an RSS or Atom feed."""
    print(f"Extracting feed: {url}")

    def fetch():
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response.content

    try:
        content = retry(fetch, exceptions=(requests.RequestException,))
    except requests.RequestException as exc:
        print(f"Feed fetch failed ({exc})", file=sys.stderr)
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        print(f"Feed parse failed ({exc})", file=sys.stderr)
        return []

    stories = []
    # RSS 2.0
    for item in root.iter("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        if title and link:
            stories.append((title, link))
        if len(stories) >= limit:
            break
    # Atom
    atom_ns = "{http://www.w3.org/2005/Atom}"
    if not stories:
        for entry in root.iter(f"{atom_ns}entry"):
            title = _text(entry, f"{atom_ns}title")
            link_el = entry.find(f"{atom_ns}link")
            link = link_el.get("href", "") if link_el is not None else ""
            if title and link:
                stories.append((title, link))
            if len(stories) >= limit:
                break
    return stories


def extract_all_stories(feed_limit=None):
    """Aggregate stories from Hacker News and configured tech news feeds."""
    if feed_limit is None:
        feed_limit = int(os.getenv("FEED_LIMIT", "8"))
    feeds = [
        feed.strip()
        for feed in os.getenv("NEWS_FEEDS", ",".join(DEFAULT_FEEDS)).split(",")
        if feed.strip()
    ]
    combined = []
    try:
        combined.extend(extract_stories())
    except (requests.RequestException, OSError) as exc:
        print(f"Hacker News scrape failed ({exc})", file=sys.stderr)
    for feed in feeds:
        combined.extend(extract_feed_stories(feed, limit=feed_limit))
    # De-duplicate by link (or title) while preserving order.
    seen = set()
    unique = []
    for title, link in combined:
        key = link or title
        if key in seen:
            continue
        seen.add(key)
        unique.append((title, link))
    try:
        limit = int(os.getenv("MAX_STORIES", str(MAX_STORIES)))
    except ValueError:
        limit = MAX_STORIES
    return unique[:limit] if limit > 0 else unique


def build_content(stories):
    """Render the story list as a polished, responsive HTML email body."""
    today = dt.datetime.now(dt.UTC).date()
    date_label = f"{today:%A, %B} {today.day}, {today.year}"

    source_counts = {}
    for _, link in stories:
        source = story_source(link)
        source_counts[source] = source_counts.get(source, 0) + 1
    summary = ", ".join(
        f"{source} ({count})" for source, count in sorted(source_counts.items())
    )
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
                '<tr><td class="pad" style="padding:8px 32px 16px;">'
                '<p style="margin:0;font-size:11px;line-height:1.5;'
                'color:#9ca3af;">Sources: ' + (summary if summary else "none") + '</p>'
                '</td></tr>'
            ),
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


def build_message(content, sender, recipients, plain_text=None):
    """Create the MIME message with a UTF-8 encoded body."""
    today = dt.datetime.now(dt.UTC).date().isoformat()
    if plain_text is not None:
        message = MIMEMultipart("alternative")
    else:
        message = MIMEMultipart()
    message["Subject"] = f"Top News Stories HN [Automated Email] {today}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    if plain_text is not None:
        message.attach(MIMEText(plain_text, "plain", "utf-8"))
    message.attach(MIMEText(content, "html", "utf-8"))
    return message


def send_email(config, content, plain_text=None):
    """Deliver the message over SMTP with STARTTLS."""
    message = build_message(content, config["sender"], config["recipients"], plain_text=plain_text)

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


def parse_args(argv=None):
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Scrape tech news and email a digest.")
    parser.add_argument("--max-stories", type=int, default=None, help="Maximum stories to send.")
    parser.add_argument("--feed-limit", type=int, default=None, help="Maximum stories per feed.")
    parser.add_argument("--include", default=None, help="Comma-separated keywords to include.")
    parser.add_argument("--exclude", default=None, help="Comma-separated keywords to exclude.")
    parser.add_argument("--plain-text", action="store_true", help="Also include a plain-text part.")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest without sending.")
    parser.add_argument("--no-dedup-db", action="store_true", help="Disable the sent-links database.")
    return parser.parse_args([] if argv is None else argv)


def _split_keywords(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def filter_stories(stories, include=None, exclude=None):
    """Filter stories by case-insensitive keyword matches."""
    include = [keyword.lower() for keyword in (include or [])]
    exclude = [keyword.lower() for keyword in (exclude or [])]
    result = []
    for title, link in stories:
        haystack = f"{title} {link}".lower()
        if include and not any(keyword in haystack for keyword in include):
            continue
        if exclude and any(keyword in haystack for keyword in exclude):
            continue
        result.append((title, link))
    return result


def story_source(link):
    """Return the netloc of a story link."""
    try:
        return urlparse(link).netloc or "unknown"
    except ValueError:
        return "unknown"


def build_text(stories):
    """Render the story list as plain text."""
    lines = ["Tech News Digest", ""]
    for rank, (title, link) in enumerate(stories, start=1):
        lines.append(f"{rank}. {title}")
        if link:
            lines.append(f"   {link}")
    return "\n".join(lines)


def sent_db_path():
    return os.getenv("SENT_DB", SENT_DB_DEFAULT)


def load_sent_links(db_path):
    try:
        connection = sqlite3.connect(db_path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sent (link TEXT PRIMARY KEY, sent_at TEXT)"
        )
        rows = connection.execute("SELECT link FROM sent").fetchall()
        connection.close()
        return {row[0] for row in rows}
    except sqlite3.Error:
        return set()


def filter_unsent_stories(db_path, stories):
    sent = load_sent_links(db_path)
    return [(title, link) for title, link in stories if (link or title) not in sent]


def record_sent_stories(db_path, stories):
    try:
        connection = sqlite3.connect(db_path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sent (link TEXT PRIMARY KEY, sent_at TEXT)"
        )
        sent_at = dt.datetime.now(dt.UTC).isoformat()
        connection.executemany(
            "INSERT OR IGNORE INTO sent (link, sent_at) VALUES (?, ?)",
            [(link or title, sent_at) for title, link in stories],
        )
        connection.commit()
        connection.close()
    except sqlite3.Error:
        pass


def main(argv=None):
    args = parse_args(argv)
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

    include = _split_keywords(os.getenv("INCLUDE_KEYWORDS", ""))
    exclude = _split_keywords(os.getenv("EXCLUDE_KEYWORDS", ""))
    if args.include:
        include.extend(_split_keywords(args.include))
    if args.exclude:
        exclude.extend(_split_keywords(args.exclude))

    feed_limit = (
        args.feed_limit
        if args.feed_limit is not None
        else int(os.getenv("FEED_LIMIT", "8"))
    )
    max_stories = (
        args.max_stories
        if args.max_stories is not None
        else int(os.getenv("MAX_STORIES", str(MAX_STORIES)))
    )

    db_path = sent_db_path()
    use_db = not args.no_dedup_db

    try:
        stories = extract_all_stories(feed_limit=feed_limit)
        stories = filter_stories(stories, include, exclude)
        if use_db:
            stories = filter_unsent_stories(db_path, stories)
        if max_stories and max_stories > 0:
            stories = stories[:max_stories]
        if not stories:
            print("No stories found; email not sent.", file=sys.stderr)
            return 1
        content = build_content(stories)
        plain_text = None
        if args.plain_text or os.getenv("PLAIN_TEXT", "").lower() in {"1", "true", "yes"}:
            plain_text = build_text(stories)
        if args.dry_run:
            print(content)
            return 0
        send_email(config, content, plain_text=plain_text)
        if use_db:
            record_sent_stories(db_path, stories)
    except (requests.RequestException, OSError, smtplib.SMTPException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
