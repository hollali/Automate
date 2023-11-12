import requests #* http requests

from bs4 import BeautifulSoup #* web scraping
#? Send the mail
import smtplib
#?email body
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
#?system date and time manipulation
import _datetime
now =_datetime.datetime.now()

#email content placeholder

content = ''


#extracting Hacking News Stories


def extract_news(url):
    print('Extracting Stories...')
    cnt=''
    cnt +=('<b> Top Stories:<b>\n'+'<br>'+'-'*50+'<br>')
    response = requests.get(url)
    content =response.content
    soup= BeautifulSoup(content,'html.parser')
    for i,tag in enumerate(soup.find_all('td',attrs={'class':'tittle','valign':''})):
        cnt +=((str(i+1)+'::'+tag.text + "\n" + '<br>') if tag.text!='More' else'')
        #print(tag.prettify) #find all('span',attrs={'class';'sitestr'})
    return(cnt)

cnt = extract_news('https://news.ycombinator.com')
content += cnt 
content += ('<br>-----<br>')
content += ('<br><br>End of Message')


#lets send the email

print('Composing Email')

#* Update your email details

SERVER ='smpt.gmail.com' #// "your smtp server"
PORT =587 # your port number
FROM = '' # "your email id"
TO = '' # "your to email ids" #*Can be a list
PASS = '****' # "your email id's password"

#fp = open(file_name, 'rb')
#Create a text/plain message
#msg = MIMETEXT('')
msg = MIMEMultipart()

#msg.add_header('Content-Disposition','attachment', filename='empty.txt')
msg['Subject'] = 'Top News Stories HN [Automated Email]' + '' + str(now.day) + '-' + str(now.month) +'-' + str(now.year)
msg['From'] = FROM
msg ['To'] = TO

msg.attach(MIMEText(content, 'html'))
#fp.close()

print('Initiating Sever...')

server = smtplib.SMTP(SERVER, PORT)
#server = smtplib.SMTP SSL('smtp.gmail.com' ,456)
server.set_debuglevel(1)
server.ehlo()
server.starttls()
#server.ehlo
server.login(FROM, PASS)
server.sendmail(FROM, TO, msg.as_string())

print('Email sent...')

server.quit()
