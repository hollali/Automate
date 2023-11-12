# Hacker News Scraper and Emailer

This Python script extracts top stories from Hacker News and sends them as an HTML-formatted email. It utilizes web scraping with BeautifulSoup for extracting news and uses the `smtplib` library for sending emails.

## Prerequisites

- Python 3.x
- Required Python packages: `requests`, `beautifulsoup4`

## Usage

1. Clone the repository:

    ```bash
    git clone https://github.com/your-username/hacker-news-emailer.git
    ```

2. Install the required Python packages:

    ```bash
    pip install requests beautifulsoup4
    ```

3. Update the script with your email credentials and recipient email address:

    ```python
    # Update your email details
    SERVER = 'smtp.gmail.com'
    PORT = 587
    FROM = 'your_email@gmail.com'
    TO = 'recipient_email@example.com'  # Can be a list
    PASS = 'your_email_password'
    ```

4. Run the script:

    ```bash
    python hacker_news_emailer.py
    ```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
