import email
import sqlite3
from email.utils import parseaddr
from email.header import decode_header
import csv
from io import StringIO
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from gpt4all import GPT4All
import tiktoken

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import time

model = GPT4All(model_name="Meta-Llama-3.1-8B-Instruct-128k-Q4_0.gguf")  # Update with the correct model name


def moveToVoid(inbox):
    print("Checking for mail to move to the void")
    
    inbox.select('The-Hole')
    
    # Search for all emails in the specified folder
    status, email_ids = inbox.search(None, 'ALL')
    if status != 'OK':
        print("No messages found.")
        return

    emailInts = email_ids[0].decode('utf-8').split()
    for num in emailInts[::-1]:
        subject, from_address, body, date = getEmailParts(inbox, num)

        # Parse the date string into a datetime object
        email_datetime = email.utils.parsedate_to_datetime(date)

        # Convert email_datetime to be timezone-aware if it's not
        if email_datetime.tzinfo is None:
            email_datetime = email_datetime.replace(tzinfo=timezone.utc)

        # Get the current date and time, make it timezone-aware
        current_datetime = datetime.now(timezone.utc)

        # Calculate the difference in days
        difference = current_datetime - email_datetime

        # Check if the email is more than a week old
        if difference > timedelta(weeks=1):
            moveEmail(inbox, num, 'The-Void')
        else:
            print(".")


####################################### organize emails #######################################

def organizeEmails(inbox, allowlist, AIRules, config):

    inbox.select('AI/to-process')
    
    # Search for all emails in the specified folder
    status, email_ids = inbox.search(None, 'ALL')
    if status != 'OK':
        print("No messages found.")
        return

    emailInts = email_ids[0].decode('utf-8').split()

    ################### move allowed emails to inbox
    print("Check for allowed emails")
    for num in emailInts[::-1]:
        subject, from_address, body, date = getEmailParts(inbox, num)

        print(num)
        #print("------")
        #print(subject)
        #print(from_address)

        if email_is_allowed(from_address, allowlist):
            print(from_address)
            if(moveEmail(inbox, num, 'INBOX')):
                emailInts.remove(num)  # Remove the email from the list
    
    
    ################### Apply AI rules
    print("Check for AI emails")
    for num in emailInts[::-1]:
        subject, from_address, body, date = getEmailParts(inbox, num)

        print("------")
        print("AI Check email: "+subject)

        for rule in AIRules:
            response = getAIResponse(rule, subject, body)

            if(response != ""):
                if(followAIRule(rule, response, inbox, num, config)): break #if the response is an action, stop trying to follow more AI rules
    

    ################### move all remaining emails from 'Processing' to 'The hole'
    for num in emailInts[::-1]:
        print("-> HOLE")

        if(moveEmail(inbox, num, 'The-Hole')):
            emailInts.remove(num)  # Remove the email from the list

    ################### execute all deletions on the server
    inbox.expunge()



####################################### update allow list #######################################

def updateAllowlist(inbox, allowlist):
    inbox.select('Sent')
    allowlistCursor = allowlist.cursor()

    # Create table to store outgoing email addresses and the last processed email ID
    allowlistCursor.execute('''
    CREATE TABLE IF NOT EXISTS allowlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_address TEXT NOT NULL,
        UNIQUE(email_address)
    )
    ''')
    
    allowlistCursor.execute('''
    CREATE TABLE IF NOT EXISTS last_processed_email (
        last_email_date TEXT
    )
    ''')

    # Get the last processed email date
    allowlistCursor.execute('SELECT last_email_date FROM last_processed_email LIMIT 1')
    row = allowlistCursor.fetchone()
    last_email_date = row[0] if row else None

    # Convert last_email_date to IMAP format if it's present
    if last_email_date:
        since_date = datetime.strptime(last_email_date, '%d-%b-%Y %H:%M:%S')
    else:
        # Default to a long time ago if no date is stored
        since_date = datetime.now() - timedelta(days=10000)

    # Format datetime for IMAP (IMAP only supports searching by date, so we need to filter by time manually later)
    since_date_str = since_date.strftime('%d-%b-%Y')

    # Search for emails since the last processed date
    status, email_ids = inbox.search(None, f'SINCE {since_date_str}')
    # Iterate over each email and extract outgoing email addresses
    if status == 'OK':
        emailInts = email_ids[0].decode('utf-8').split()
        last_processed_datetime = ""

        for num in emailInts:
            msg = getMsg(inbox, num)

            if(msg == ""):
                continue

            # Get the email's date
            email_date_str = msg.get('Date')
            email_date = datetime.strptime(email_date_str[:-6], '%a, %d %b %Y %H:%M:%S')  # Remove timezone info
            last_processed_datetime = email_date.strftime('%d-%b-%Y %H:%M:%S')

            # Only process emails that are newer than the last processed datetime
            if email_date <= since_date:
                continue

            # Extract email addresses from the 'To', 'Cc', and 'Bcc' fields
            outgoing_addresses = extract_email_addresses(msg)

            # Insert the outgoing addresses into the database if not already present
            for address in outgoing_addresses:
                try:
                    allowlistCursor.execute('INSERT OR IGNORE INTO allowlist (email_address) VALUES (?)', (address,))
                except sqlite3.IntegrityError:
                    pass
            allowlist.commit()

        # Update the last processed email datetime
        # Drop and recreate the last_processed_email table
        allowlistCursor.execute('DROP TABLE IF EXISTS last_processed_email')
        allowlistCursor.execute('''
        CREATE TABLE last_processed_email (
            last_email_date TEXT
        )
        ''')
        allowlistCursor.execute('INSERT OR REPLACE INTO last_processed_email (last_email_date) VALUES (?)', (last_processed_datetime,))
        allowlist.commit()
        print('Updated allowlist.')

####################################### helper functions #######################################

# Function to validate email addresses
def is_valid_email(email_address):
    # Basic regex for email validation
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(email_regex, email_address) is not None

# Function to extract email addresses from 'To', 'Cc', and 'Bcc' fields
def extract_email_addresses(msg):
    addresses = set()  # Use a set to avoid duplicates
    for header in ['To', 'Cc', 'Bcc']:
        header_value = ''.join(msg.get(header, '').split())
     
        if not header_value:
            continue

        # Use StringIO to treat the string as a file
        IOheader = StringIO(header_value)
        # Use csv.reader to handle the splitting
        CSVheader = csv.reader(IOheader, delimiter=',', quotechar='"')
        for split_emails in CSVheader:
            valid_emails = (parseaddr(addr)[1] for addr in split_emails if is_valid_email(parseaddr(addr)[1]))
            addresses.update(valid_emails)

    print(addresses)
    return list(addresses)

# Function to extract email addresses from 'To', 'Cc', and 'Bcc' fields
def get_from_address(msg):
    addresses = set()  # Use a set to avoid duplicates
    for header in ['From']:
        header_value = ''.join(msg.get(header, '').split())
     
        if not header_value:
            continue

        # Use StringIO to treat the string as a file
        IOheader = StringIO(header_value)
        # Use csv.reader to handle the splitting
        CSVheader = csv.reader(IOheader, delimiter=',', quotechar='"')
        for split_emails in CSVheader:
            valid_emails = (parseaddr(addr)[1] for addr in split_emails if is_valid_email(parseaddr(addr)[1]))
            addresses.update(valid_emails)

    print(addresses)
    return list(addresses)

def email_is_allowed(email, allowlist):
    cursor = allowlist.cursor()

    # Query to check if the email exists
    cursor.execute('SELECT 1 FROM allowlist WHERE email_address = ?', (email,))
    result = cursor.fetchone()

    if result:
        return True
    else:
        return False
    
def getBody(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            # If part is text/plain or text/html, extract it
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset()
                if charset is None:
                    charset = "utf-8"  # Default to utf-8 if charset is not specified
                body = part.get_payload(decode=True).decode(charset, errors="ignore")
                break
            elif part.get_content_type() == "text/html":
                charset = part.get_content_charset()
                if charset is None:
                    charset = "utf-8"  # Default to utf-8 if charset is not specified
                html_content = part.get_payload(decode=True).decode(charset, errors="ignore")
                # Use BeautifulSoup to strip HTML tags
                soup = BeautifulSoup(html_content, "html.parser")
                body = soup.get_text()
                break
    else:
        # If it's a single-part email
        charset = msg.get_content_charset()
        if charset is None:
            charset = "utf-8"  # Default to utf-8 if charset is not specified
        content_type = msg.get_content_type()
        body = msg.get_payload(decode=True).decode(charset, errors="ignore")
        if content_type == "text/html":
            soup = BeautifulSoup(body, "html.parser")
            body = soup.get_text()
    return body

def moveEmail(inbox, num, location):
    print("-> "+location)
    result = inbox.copy(num, location)
    if result[0] == 'OK':
        inbox.store(num, '+FLAGS', '\\Deleted')
        inbox.expunge()
        return True
    return False

def fwd_email(inbox, email_id, from_addr, to_addr, config):

    IMAP_SERVER, SMTP_SERVER, EMAIL_ACCOUNT, PASSWORD = config

    # Fetch the email
    status, data = inbox.fetch(email_id, '(RFC822)')
    raw_email = data[0][1]
    original_msg = email.message_from_bytes(raw_email)

    # Create a new email message object for forwarding
    forward_msg = MIMEMultipart()
    forward_msg['From'] = from_addr
    forward_msg['To'] = to_addr
    forward_msg['Subject'] = 'Fwd: ' + original_msg['Subject']

    # Forward the original email's body and add a custom message
    body = f"Forwarded message:\n\nFrom: {original_msg['From']}\nSubject: {original_msg['Subject']}\n\n"
    for part in original_msg.walk():
        if part.get_content_type() == "text/plain" or part.get_content_type() == "text/html":
            body += part.get_payload(decode=True).decode(part.get_content_charset())

    forward_msg.attach(MIMEText(body, 'plain'))

    # Forward any attachments
    for part in original_msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        attachment = MIMEBase(part.get_content_type(), part.get_content_subtype())
        attachment.set_payload(part.get_payload(decode=True))
        encoders.encode_base64(attachment)
        attachment.add_header('Content-Disposition', part.get('Content-Disposition'))
        forward_msg.attach(attachment)

    # Send the forwarded email via SMTP
    text = forward_msg.as_string()


    outbox = smtplib.SMTP(SMTP_SERVER, 587)
    outbox.starttls()
    outbox.login(EMAIL_ACCOUNT, PASSWORD)
    outbox.sendmail(from_addr, to_addr, text)
    outbox.quit()
    
def trim_string(input_string):
    tokenizer = tiktoken.get_encoding("cl100k_base")  # I know this is wrong but it's rough

    # Tokenize the string
    tokens = tokenizer.encode(input_string)

    # Cut off at 1800 tokens
    tokens = tokens[:1800]

    # Convert tokens back to string
    trimmed_string = tokenizer.decode(tokens)

    return trimmed_string

def getAIResponse(rule, subj, body, retries=3, delay=5):
    print("--->Check rule: " + rule['name'])

    prompt = rule['prompt'] + "\nSubject:" + subj + "\nBody:\n" + trim_string(body.replace('\n', ''))

    for attempt in range(retries):
        try:
            with model.chat_session(system_prompt="<|start_header_id|>system<|end_header_id|>\nCutting Knowledge Date: December 2023\nYou are a helpful assistant.<|eot_id|>"):
                response = model.generate(prompt, max_tokens=40, temp = 1)
            return response

        except (TimeoutError, ConnectionError) as e:
            print(f"Error: {e}. Retrying {attempt + 1}/{retries}...")
            time.sleep(delay)  # Wait before retrying

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return ""

    return ""

def followAIRule(rule, resp, inbox, num, config):
    reactions = rule['reactions']

    #print("*********\n"+resp+"\n************")

    for reaction in reactions:
        if(reaction[0] in resp):
            print(reaction[0])
            
            for action in reaction[1]:
                a = action.split(":")
                if(a[0] == "move"):
                    print("move ->"+a[1])
                    moveEmail(inbox, num, a[1])
                if(a[0] == "mark"):
                    if(a[1] == "read"):
                        inbox.store(num, '+FLAGS', '\\Seen')
                if(a[0] == "fwd"):
                    IMAP_SERVER, SMTP_SERVER, EMAIL_ACCOUNT, PASSWORD = config
                    fwd_email(inbox, num, EMAIL_ACCOUNT, a[1], config)
                    
            
            return reaction[0].startswith('no') == False
            
    return False

def decode_header_value(value):
    if isinstance(value, email.header.Header):
        # Decode the header into a readable string
        decoded_bytes, charset = decode_header(value)[0]
        if charset is None or charset.lower() in ["unknown-8bit", "x-unknown"]:
            # Handle the unknown encoding case
            charset = "utf-8"  # Default to utf-8 if charset is not specified or is unknown
        try:
            return decoded_bytes.decode(charset)
        except LookupError:
            # If the charset is not recognized, decode as utf-8
            return decoded_bytes.decode("utf-8", errors="ignore")
    return value

def getMsg(inbox, num):
    status, data = inbox.fetch(str(num), '(BODY.PEEK[])')
        
    # error handling to avoid issues ########################################
    if status != 'OK':
        print(f"Failed to fetch email ID {num}. Skipping...")
        return ""

    # Debugging: Check if data is in the expected format
    if not isinstance(data[0], tuple):
        print(f"Unexpected data format for email ID {num}: {data}")
        return ""


    raw_email = data[0][1]

    
    try:
        msg = email.message_from_bytes(raw_email)
    except Exception as e:
        print(f"Error parsing email ID {num}: {e}")
        return ""
    

    return msg

def getEmailParts(inbox, num):

    subject = ""
    from_address = ""
    body = ""
    date = ""

    msg = getMsg(inbox, num)

    if(msg == ""):
        return [subject, from_address, body, date]

    subject = msg['subject']
    from_header = msg.get('From')
    from_address = parseaddr(decode_header_value(from_header))[1]
    body = getBody(msg)
    date = msg.get('Date')

    return [subject, from_address, body, date]