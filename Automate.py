import requests  # HTTP requests
from bs4 import BeautifulSoup  # Web scraping
import smtplib  # Email sending
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime as dt

# Email content placeholder
content = ''

def extract_news(url):
    print('Extracting Stories...')
    cnt = ''
    cnt += '<b>Top Stories:</b><br>' + '-'*50 + '<br>'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    for i, tag in enumerate(soup.find_all('td', attrs={'class': 'title', 'valign': ''})):
        if tag.text != 'More':
            cnt += f'{i+1}::{tag.text}<br>'
    return cnt

cnt = extract_news('https://news.ycombinator.com')
content += cnt
content += '<br>-----<br>'
content += '<br><br>End of Message'

# Email details
SERVER = 'smtp.gmail.com'
PORT = 587
FROM = ''  # Your email id
TO = ''  # Recipient email id(s) - Can be a list
PASS = '****'  # Your email password

# Compose email
msg = MIMEMultipart()
msg['Subject'] = f'Top News Stories HN [Automated Email] {dt.datetime.now().day}-{dt.datetime.now().month}-{dt.datetime.now().year}'
msg['From'] = FROM
msg['To'] = TO
msg.attach(MIMEText(content, 'html'))

try:
    print('Initiating Server...')
    server = smtplib.SMTP(SERVER, PORT)
    server.set_debuglevel(1)
    server.ehlo()
    server.starttls()
    server.login(FROM, PASS)
    server.sendmail(FROM, TO, msg.as_string())
    print('Email sent...')
except Exception as e:
    print(f'Error: {e}')
finally:
    server.quit()
