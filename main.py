from telethon import TelegramClient, sync, errors
from telethon.tl.functions.channels import ReportChannelRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonViolence, InputReportReasonPornography
from telethon.tl.types import InputReportReasonChildAbuse, InputReportReasonCopyright, InputReportReasonGeoIrrelevant
from telethon.tl.types import InputReportReasonFake, InputReportReasonIllegalDrugs, InputReportReasonPersonalDetails
from telethon.tl.types import InputReportReasonOther
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChannelInvalidError
from concurrent.futures import ThreadPoolExecutor
import logging
import asyncio
import argparse
import json
import os
import sys
import time
import random
import getpass
import csv
from datetime import datetime
from colorama import Fore, Style, init
from tqdm import tqdm
import configparser
import re

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("telegram_reporter.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Global configuration
class Config:
    # API credentials - get from https://my.telegram.org/auth
    API_ID = 0
    API_HASH = ""
    THREAD_COUNT = 3
    MAX_RETRY = 3
    WAIT_TIME_MIN = 2
    WAIT_TIME_MAX = 5
    
    # Statistics
    successful_reports = 0
    failed_reports = 0
    blocked_accounts = []
    working_accounts = {}
    
    # Session directory
    SESSION_DIR = "sessions"

# ASCII Art for the application
BANNER = f"""
{Fore.CYAN}████████╗███████╗██╗     ███████╗ ██████╗ ██████╗  █████╗ ███╗   ███╗
{Fore.CYAN}╚══██╔══╝██╔════╝██║     ██╔════╝██╔════╝ ██╔══██╗██╔══██╗████╗ ████║
{Fore.CYAN}   ██║   █████╗  ██║     █████╗  ██║  ███╗██████╔╝███████║██╔████╔██║
{Fore.CYAN}   ██║   ██╔══╝  ██║     ██╔══╝  ██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║
{Fore.CYAN}   ██║   ███████╗███████╗███████╗╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
{Fore.CYAN}   ╚═╝   ╚══════╝╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
                                                                           
{Fore.RED}██████╗ ███████╗██████╗  ██████╗ ██████╗ ████████╗███████╗██████╗ 
{Fore.RED}██╔══██╗██╔════╝██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝██╔══██╗
{Fore.RED}██████╔╝█████╗  ██████╔╝██║   ██║██████╔╝   ██║   █████╗  ██████╔╝
{Fore.RED}██╔══██╗██╔══╝  ██╔═══╝ ██║   ██║██╔══██╗   ██║   ██╔══╝  ██╔══██╗
{Fore.RED}██║  ██║███████╗██║     ╚██████╔╝██║  ██║   ██║   ███████╗██║  ██║
{Fore.RED}╚═╝  ╚═╝╚══════╝╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
{Fore.YELLOW}Advanced Mass Reporting Tool for Telegram Channels v1.0
"""

# Load and save configuration
def load_config():
    config = configparser.ConfigParser()
    config_file = 'config.ini'
    
    if os.path.exists(config_file):
        config.read(config_file)
        if 'Telegram' in config:
            Config.API_ID = config.getint('Telegram', 'api_id', fallback=0)
            Config.API_HASH = config.get('Telegram', 'api_hash', fallback="")
        if 'Settings' in config:
            Config.THREAD_COUNT = config.getint('Settings', 'threads', fallback=3)
            Config.MAX_RETRY = config.getint('Settings', 'max_retry', fallback=3)
            Config.WAIT_TIME_MIN = config.getfloat('Settings', 'wait_min', fallback=2)
            Config.WAIT_TIME_MAX = config.getfloat('Settings', 'wait_max', fallback=5)
        
        logger.info(f"Loaded configuration from {config_file}")
    
    # If values are still default, prompt user
    if Config.API_ID == 0 or not Config.API_HASH:
        print(f"{Fore.YELLOW}\nAPI credentials are required from https://my.telegram.org/auth")
        Config.API_ID = int(input(f"{Fore.GREEN}Enter API ID: {Style.RESET_ALL}"))
        Config.API_HASH = input(f"{Fore.GREEN}Enter API Hash: {Style.RESET_ALL}")
        
        # Save to config file
        if not config.has_section('Telegram'):
            config.add_section('Telegram')
        config['Telegram']['api_id'] = str(Config.API_ID)
        config['Telegram']['api_hash'] = Config.API_HASH
        
        if not config.has_section('Settings'):
            config.add_section('Settings')
        config['Settings']['threads'] = str(Config.THREAD_COUNT)
        config['Settings']['max_retry'] = str(Config.MAX_RETRY)
        config['Settings']['wait_min'] = str(Config.WAIT_TIME_MIN)
        config['Settings']['wait_max'] = str(Config.WAIT_TIME_MAX)
        
        with open(config_file, 'w') as f:
            config.write(f)
        logger.info(f"Saved configuration to {config_file}")

# Save and load account data
def save_account_data():
    data = {
        "working_accounts": Config.working_accounts,
        "blocked_accounts": Config.blocked_accounts,
        "successful_reports": Config.successful_reports,
        "failed_reports": Config.failed_reports
    }
    with open("account_data.json", "w") as f:
        json.dump(data, f)
    logger.info(f"Account data saved to account_data.json")

def load_account_data():
    if os.path.exists("account_data.json"):
        try:
            with open("account_data.json", "r") as f:
                data = json.load(f)
                Config.working_accounts = data.get("working_accounts", {})
                Config.blocked_accounts = data.get("blocked_accounts", [])
                Config.successful_reports = data.get("successful_reports", 0)
                Config.failed_reports = data.get("failed_reports", 0)
            logger.info(f"Account data loaded from account_data.json")
            logger.info(f"Total working accounts: {len(Config.working_accounts)}")
            logger.info(f"Total blocked accounts: {len(Config.blocked_accounts)}")
        except Exception as e:
            logger.error(f"Failed to load account data: {str(e)}")

# Random delay to simulate human behavior
def random_delay(min_time=None, max_time=None):
    min_t = min_time if min_time is not None else Config.WAIT_TIME_MIN
    max_t = max_time if max_time is not None else Config.WAIT_TIME_MAX
    delay_time = random.uniform(min_t, max_t)
    time.sleep(delay_time)
    return delay_time

# Get reason for reporting
def get_report_reason(reason_code):
    reasons = {
        "1": {"type": InputReportReasonSpam(), "name": "Spam"},
        "2": {"type": InputReportReasonViolence(), "name": "Violence"},
        "3": {"type": InputReportReasonPornography(), "name": "Pornography"},
        "4": {"type": InputReportReasonChildAbuse(), "name": "Child Abuse"},
        "5": {"type": InputReportReasonCopyright(), "name": "Copyright"},
        "6": {"type": InputReportReasonGeoIrrelevant(), "name": "Geo-Irrelevant"},
        "7": {"type": InputReportReasonFake(), "name": "Fake Account"},
        "8": {"type": InputReportReasonIllegalDrugs(), "name": "Illegal Drugs"},
        "9": {"type": InputReportReasonPersonalDetails(), "name": "Personal Details"},
        "10": {"type": InputReportReasonOther(), "name": "Other"}
    }
    return reasons.get(reason_code, {"type": InputReportReasonSpam(), "name": "Spam"})

# Validate phone number format
def validate_phone(phone):
    # Clean up the phone number
    phone = re.sub(r'\D', '', phone)
    
    # Add + if missing
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # Basic validation
    if len(phone) < 8:
        return None
    
    return phone

async def report_channel(account, target_channel, reason_code):
    phone = account["phone"]
    
    # Skip blocked accounts
    if phone in Config.blocked_accounts:
        logger.warning(f"Account {phone} is blocked. Skipping...")
        return False
    
    # Check if the session directory exists
    if not os.path.exists(Config.SESSION_DIR):
        os.makedirs(Config.SESSION_DIR)
    
    # Create a session file name
    session_file = os.path.join(Config.SESSION_DIR, f"session_{re.sub(r'\D', '', phone)}")
    
    # Get the reason
    reason_data = get_report_reason(reason_code)
    reason = reason_data["type"]
    reason_name = reason_data["name"]
    
    logger.info(f"Attempting to report {target_channel} with account {phone} for {reason_name}")
    
    # Create the client
    client = TelegramClient(session_file, Config.API_ID, Config.API_HASH)
    
    try:
        # Connect to Telegram
        await client.connect()
        
        # Check if already authorized
        if not await client.is_user_authorized():
            logger.info(f"Sending code to {phone}")
            
            # Send code
            try:
                await client.send_code_request(phone)
            except FloodWaitError as e:
                logger.error(f"FloodWaitError for {phone}: Need to wait {e.seconds} seconds")
                Config.blocked_accounts.append(phone)
                await client.disconnect()
                return False
            
            # Get authentication code from user
            code = input(f"{Fore.GREEN}Enter the code received on {phone}: {Style.RESET_ALL}")
            
            # Sign in
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = getpass.getpass(f"{Fore.YELLOW}Two-step verification enabled. Enter your password: {Style.RESET_ALL}")
                await client.sign_in(password=password)
        
        # Store working account
        me = await client.get_me()
        user_id = me.id
        username = me.username if me.username else "No Username"
        Config.working_accounts[phone] = {"user_id": user_id, "username": username}
        
        # Report the channel
        try:
            # Make sure target_channel starts with @ if it's a username
            if not target_channel.startswith('@') and not target_channel.startswith('https://') and not target_channel.isdigit():
                target_channel = '@' + target_channel
            
            # Try to report
            try:
                result = await client(ReportChannelRequest(
                    channel=target_channel,
                    reason=reason,
                    message="This channel violates Telegram's Terms of Service"
                ))
                
                if result:
                    logger.info(f"Successfully reported {target_channel} with account {phone}")
                    Config.successful_reports += 1
                    await client.disconnect()
                    return True
                else:
                    logger.warning(f"Report result unclear for {target_channel} with account {phone}")
                    Config.failed_reports += 1
                    await client.disconnect()
                    return False
                    
            except ChannelInvalidError:
                logger.error(f"Channel {target_channel} is invalid or not accessible")
                Config.failed_reports += 1
            except errors.FloodWaitError as e:
                logger.error(f"FloodWaitError: Need to wait {e.seconds} seconds for account {phone}")
                Config.blocked_accounts.append(phone)
                Config.failed_reports += 1
            except Exception as e:
                logger.error(f"Error reporting channel with account {phone}: {str(e)}")
                Config.failed_reports += 1
        
        except Exception as e:
            logger.error(f"Error during reporting with account {phone}: {str(e)}")
            Config.failed_reports += 1
    
    except Exception as e:
        logger.error(f"Error connecting with account {phone}: {str(e)}")
        Config.failed_reports += 1
    
    finally:
        await client.disconnect()
    
    return False

def get_input_accounts():
    parser = argparse.ArgumentParser(description='Telegram Channel Reporter')
    parser.add_argument('--file', help='Load accounts from CSV/JSON file')
    parser.add_argument('--max', type=int, default=50, help='Maximum number of accounts to process')
    parser.add_argument('--threads', type=int, default=3, help='Number of threads to use')
    parser.add_argument('--target', help='Target channel to report')
    args = parser.parse_args()
    
    Config.THREAD_COUNT = args.threads
    
    accounts = []
    
    # Load accounts from file if specified
    if args.file:
        try:
            if args.file.endswith('.json'):
                with open(args.file, 'r') as f:
                    file_accounts = json.load(f)
                    if isinstance(file_accounts, list):
                        accounts = file_accounts
                        logger.info(f"Successfully loaded {len(accounts)} accounts from {args.file}")
                        return accounts, args.target
            elif args.file.endswith('.csv'):
                with open(args.file, 'r') as f:
                    csv_reader = csv.DictReader(f)
                    for row in csv_reader:
                        if 'phone' in row:
                            phone = validate_phone(row['phone'])
                            if phone:
                                accounts.append({"phone": phone})
                    logger.info(f"Successfully loaded {len(accounts)} accounts from {args.file}")
                    return accounts, args.target
        except Exception as e:
            logger.error(f"Failed to load accounts from file: {str(e)}")
    
    # Get accounts from user input
    print(BANNER)
    print(f"{Fore.GREEN}Telegram Channel Reporter - Mass Reporting Tool\n")
    
    max_accounts = args.max
    default_target = args.target
    
    # Get target first if not provided
    if not default_target:
        default_target = input(f"{Fore.CYAN}Enter target channel username or link: {Style.RESET_ALL}")
    
    print(f"\n{Fore.YELLOW}Report reasons:{Style.RESET_ALL}")
    print("1. Spam")
    print("2. Violence")
    print("3. Pornography")
    print("4. Child Abuse")
    print("5. Copyright")
    print("6. Geo-Irrelevant")
    print("7. Fake Account")
    print("8. Illegal Drugs")
    print("9. Personal Details")
    print("10. Other")
    
    reason_code = input(f"\n{Fore.CYAN}Select report reason (1-10): {Style.RESET_ALL}")
    
    print(f"\n{Fore.YELLOW}Enter phone numbers for accounts to use for reporting.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Format: +1234567890 (with country code){Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Press Enter with no input when done.{Style.RESET_ALL}\n")
    
    for i in range(max_accounts):
        try:
            phone_input = input(f"{Fore.GREEN}Enter phone #{i+1}: {Style.RESET_ALL}")
            if not phone_input:
                break
            
            phone = validate_phone(phone_input)
            if not phone:
                print(f"{Fore.RED}Invalid phone number format. Use format like +1234567890{Style.RESET_ALL}")
                continue
            
            accounts.append({
                "phone": phone,
                "reason_code": reason_code
            })
        
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Input stopped by user.{Style.RESET_ALL}")
            break
        
        except Exception as e:
            logger.error(f"Error during input: {str(e)}")
    
    return accounts, default_target

def display_statistics():
    print("\n" + "="*60)
    print(f"{Fore.CYAN}### REPORTING STATISTICS ###{Style.RESET_ALL}")
    print("="*60)
    print(f"Total working accounts: {len(Config.working_accounts)}")
    print(f"Total blocked accounts: {len(Config.blocked_accounts)}")
    print(f"Total successful reports: {Config.successful_reports}")
    print(f"Total failed reports: {Config.failed_reports}")
    
    if Config.working_accounts:
        print(f"\n{Fore.GREEN}### Working Accounts ###{Style.RESET_ALL}")
        for i, (phone, data) in enumerate(Config.working_accounts.items(), 1):
            username = data.get("username", "No Username")
            print(f"{i}. Phone: {phone}, Username: {username}")
    
    if Config.blocked_accounts:
        print(f"\n{Fore.RED}### Blocked Accounts ###{Style.RESET_ALL}")
        for i, phone in enumerate(Config.blocked_accounts, 1):
            print(f"{i}. {phone}")
    
    print("="*60)

async def process_account(account, target_channel):
    reason_code = account.get("reason_code", "1")  # Default to spam if not specified
    retry_count = 0
    
    while retry_count < Config.MAX_RETRY:
        try:
            result = await report_channel(account, target_channel, reason_code)
            return result
        except Exception as e:
            logger.error(f"Error in process_account: {str(e)}")
            retry_count += 1
            await asyncio.sleep(random.uniform(1, 3))
    
    return False

async def main_async():
    # Load configuration
    load_config()
    
    # Load previous account data
    load_account_data()
    
    # Get accounts and target
    accounts, target_channel = get_input_accounts()
    
    if not accounts:
        logger.warning("No accounts entered. Exiting.")
        return
    
    if not target_channel:
        logger.warning("No target channel specified. Exiting.")
        return
    
    logger.info(f"Total accounts to use: {len(accounts)}")
    logger.info(f"Target channel: {target_channel}")
    
    # Process accounts with asyncio tasks
    tasks = []
    for account in accounts:
        tasks.append(process_account(account, target_channel))
    
    # Run with progress bar
    with tqdm(total=len(tasks), desc="Reporting Progress") as pbar:
        for task in asyncio.as_completed(tasks):
            await task
            pbar.update(1)
    
    print(f"\n{Fore.GREEN}Reporting process complete!{Style.RESET_ALL}")
    
    # Save account data
    save_account_data()
    
    # Display statistics
    display_statistics()

def main():
    try:
        # Run the async main
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Program stopped by user.{Style.RESET_ALL}")
        # Save account data on exit
        save_account_data()
        display_statistics()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        # Save account data on error
        save_account_data()

if __name__ == "__main__":
    main()