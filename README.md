# Hacker News Scraper and Emailer

`Automate.py` scrapes the Hacker News front page and emails the top stories as an HTML message.

## What it does

- Fetches `https://news.ycombinator.com` with a timeout and a User-Agent.
- Extracts story titles and links, numbering them without gaps.
- Escapes titles and URLs, then sends a UTF-8 HTML email over SMTP with STARTTLS.
- Retries transient network failures and never sends an empty email.
- Reads all credentials from environment variables — nothing is stored in source.

## Requirements

- Python 3.x
- `requests` and `beautifulsoup4` (install with `pip install -r requirements.txt`)

## Setup

1. Clone the repository and install dependencies:

    ```bash
    git clone https://github.com/hollali/Automate.git
    cd Automate
    pip install -r requirements.txt
    ```

2. Create a Gmail **App Password** in your Google Account security settings (requires 2-Step Verification). A regular account password will not work with SMTP login.

3. Export your settings:

    ```bash
    export EMAIL_FROM="your_email@gmail.com"
    export EMAIL_TO="recipient@example.com,another@example.com"
    export EMAIL_PASSWORD="your_app_password"
    ```

    `EMAIL_TO` accepts one address or a comma-separated list. Optional overrides: `SMTP_SERVER` (default `smtp.gmail.com`) and `SMTP_PORT` (default `587`).

4. Run the script:

    ```bash
    ./Automate.py
    ```

   To automate it, schedule it with cron; make sure the environment variables are available to the cron job, for example:

    ```cron
    0 8 * * * cd /path/to/Automate && EMAIL_FROM="you@gmail.com" EMAIL_TO="me@example.com" EMAIL_PASSWORD="app_password" ./Automate.py
    ```

## License

MIT — see [LICENSE](LICENSE).
