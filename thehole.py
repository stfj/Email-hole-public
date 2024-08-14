import imaplib
import smtplib
import sqlite3
import configparser
import yaml
import os
import time
from datetime import datetime, timedelta

from allowlist import updateAllowlist, organizeEmails, moveToVoid

LOCK_FILE = 'script.lock'

def check_and_create_lock():
    if os.path.exists(LOCK_FILE):
        # Check the age of the lock file
        lock_time = datetime.fromtimestamp(os.path.getmtime(LOCK_FILE))
        if datetime.now() - lock_time < timedelta(hours=1):
            print("Script is already running or was run recently. Exiting.")
            return False
        else:
            print("Lock file is older than an hour. Proceeding with execution.")
    # Create or update the lock file
    with open(LOCK_FILE, 'w') as lock_file:
        lock_file.write("This file is used to lock the script execution.")
    return True

def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def loadConfig():
    # IMAP server details
    # Create a ConfigParser object
    config = configparser.ConfigParser()

    # Read the configuration file
    config.read('config.cfg')

    # Load the values from the 'email' section
    IMAP_SERVER = config.get('email', 'IMAP_SERVER')
    SMTP_SERVER = config.get('email', 'SMTP_SERVER')
    EMAIL_ACCOUNT = config.get('email', 'EMAIL_ACCOUNT')
    PASSWORD = config.get('email', 'PASSWORD')

    return [IMAP_SERVER, SMTP_SERVER, EMAIL_ACCOUNT, PASSWORD]

def connectToMail(IMAP_SERVER, EMAIL_ACCOUNT, PASSWORD):
    # Connect to the email server
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, PASSWORD)

    return mail


def loadAIRules():
    # Define the path to your YAML file
    yaml_file_path = 'AIRules.yaml'

    # Read and parse the YAML file
    with open(yaml_file_path, 'r') as file:
        config = yaml.safe_load(file)

    # Access the rules
    rules = config['rules']

    return rules

######################################### Main #########################################

if not check_and_create_lock():
    exit()

try:
    config = loadConfig()

    IMAP_SERVER, SMTP_SERVER, EMAIL_ACCOUNT, PASSWORD = config

    inbox = connectToMail(IMAP_SERVER, EMAIL_ACCOUNT, PASSWORD)

    allowlist = sqlite3.connect('allowlist.db')

    updateAllowlist(inbox, allowlist)

    AIRules = loadAIRules()

    # Start parsing emails
    organizeEmails(inbox, allowlist, AIRules, config)

    # Move old emails from the hole into the void
    moveToVoid(inbox)

    # Close the database connection and logout from the mail server
    allowlist.close()
    inbox.logout()

finally:
    remove_lock()