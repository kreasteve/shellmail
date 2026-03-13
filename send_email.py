#!/usr/bin/env python3
"""
Shell Email Tool
Supports SMTP sending and IMAP reading
"""

import smtplib
import imaplib
import argparse
import sys
import os
import json
import csv
import time
import select as _select
import email as email_module
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import decode_header
from pathlib import Path


# Config: first check next to script (dot-prefixed), then home directory
_SCRIPT_DIR = Path(__file__).resolve().parent
_LOCAL_CONFIG = _SCRIPT_DIR / ".email_config.json"
_HOME_CONFIG = Path.home() / ".email_config.json"
CONFIG_FILE = _LOCAL_CONFIG if _LOCAL_CONFIG.exists() else _HOME_CONFIG

# Exit codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_SEND_ERROR = 2
EXIT_VALIDATION_ERROR = 3
EXIT_FILE_ERROR = 4


def validate_email(email):
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def output_result(result, json_mode=False):
    """Output result in JSON or human-readable format"""
    if json_mode:
        print(json.dumps(result, indent=2))
    else:
        if result.get('status') == 'success':
            print(f"✓ {result.get('message', 'Success')}")
        elif result.get('status') == 'error':
            print(f"✗ {result.get('message', 'Error')}", file=sys.stderr)
        elif result.get('status') == 'batch':
            print(f"Batch send results:")
            print(f"  Total: {result['total']}")
            print(f"  Success: {result['success']}")
            print(f"  Failed: {result['failed']}")
            if result.get('details'):
                for detail in result['details']:
                    status = "✓" if detail['status'] == 'success' else "✗"
                    print(f"    {status} {detail['to']}: {detail.get('message', '')}")


def load_config():
    """Load configuration from file"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config: {e}", file=sys.stderr)
    return {}


def save_config(config):
    """Save configuration to file (prefers script directory)"""
    save_path = _LOCAL_CONFIG
    try:
        with open(save_path, 'w') as f:
            json.dump(config, f, indent=2)
        # Set permissions to 600 (only user can read/write)
        save_path.chmod(0o600)
        return True
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)
        return False


def setup_config():
    """Interactive configuration setup"""
    print("=" * 60)
    print("   Email Configuration Setup")
    print("=" * 60)
    print()
    print("Your credentials will be saved to:")
    print(f"  {_LOCAL_CONFIG}")
    print()

    config = {}

    # SMTP Provider selection
    print("Common providers:")
    print("1) Gmail (smtp.gmail.com)")
    print("2) Outlook/Hotmail (smtp-mail.outlook.com)")
    print("3) Strato (smtp.strato.de)")
    print("4) Custom")
    print()

    choice = input("Choose provider [1-4] (default: 4): ").strip() or "4"

    if choice == "1":
        config["smtp_host"] = "smtp.gmail.com"
        config["smtp_port"] = 587
        config["smtp_tls"] = True
        config["imap_host"] = "imap.gmail.com"
        config["imap_port"] = 993
        config["imap_ssl"] = True
    elif choice == "2":
        config["smtp_host"] = "smtp-mail.outlook.com"
        config["smtp_port"] = 587
        config["smtp_tls"] = True
        config["imap_host"] = "outlook.office365.com"
        config["imap_port"] = 993
        config["imap_ssl"] = True
    elif choice == "3":
        config["smtp_host"] = "smtp.strato.de"
        config["smtp_port"] = 587
        config["smtp_tls"] = True
        config["imap_host"] = "imap.strato.de"
        config["imap_port"] = 993
        config["imap_ssl"] = True
    else:
        config["smtp_host"] = input("SMTP Host: ").strip()
        config["smtp_port"] = int(input("SMTP Port (default: 587): ").strip() or "587")
        tls = input("Use TLS? [Y/n]: ").strip().lower()
        config["smtp_tls"] = tls != 'n'
        imap_host = input("IMAP Host (leave blank to skip): ").strip()
        if imap_host:
            config["imap_host"] = imap_host
            config["imap_port"] = int(input("IMAP Port (default: 993): ").strip() or "993")
            imap_ssl = input("IMAP SSL? [Y/n]: ").strip().lower()
            config["imap_ssl"] = imap_ssl != 'n'

    print()
    config["smtp_user"] = input("SMTP Username/Email: ").strip()
    config["smtp_pass"] = input("SMTP Password: ").strip()
    config["smtp_from"] = input(f"From Email (default: {config['smtp_user']}): ").strip() or config["smtp_user"]
    default_to = input("Default recipient email (optional): ").strip()
    if default_to:
        config["default_to"] = default_to

    print()
    print("Saving configuration...")

    if save_config(config):
        print("✓ Configuration saved!")
        print()
        print("Test with:")
        print(f"  ./send_email.py -t someone@example.com -s 'Test' -m 'Hello'")
    else:
        print("✗ Failed to save configuration", file=sys.stderr)
        return False

    return True


def send_email(smtp_host, smtp_port, from_email, to_email, subject,
               text=None, html=None, attachments=None,
               use_tls=False, username=None, password=None):
    """
    Send email via SMTP

    Returns: dict with status, message, timestamp, etc.
    """
    start_time = time.time()

    # Validate email
    if not validate_email(to_email):
        return {
            'status': 'error',
            'code': EXIT_VALIDATION_ERROR,
            'message': f'Invalid email address: {to_email}',
            'to': to_email,
            'timestamp': datetime.now().isoformat()
        }

    # Create message
    msg = MIMEMultipart('alternative')
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    # Attach text body
    if text:
        msg.attach(MIMEText(text, 'plain'))

    # Attach HTML body
    if html:
        msg.attach(MIMEText(html, 'html'))

    # Attach files
    attached_files = []
    if attachments:
        for file_path in attachments:
            if not Path(file_path).exists():
                return {
                    'status': 'error',
                    'code': EXIT_FILE_ERROR,
                    'message': f'Attachment not found: {file_path}',
                    'to': to_email,
                    'timestamp': datetime.now().isoformat()
                }

            with open(file_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = Path(file_path).name
                part.add_header('Content-Disposition',
                               f'attachment; filename={filename}')
                msg.attach(part)
                attached_files.append(filename)

    # Send email
    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)

        if username and password:
            server.login(username, password)

        server.send_message(msg)
        message_id = msg.get('Message-ID', '')
        server.quit()

        elapsed = time.time() - start_time

        return {
            'status': 'success',
            'code': EXIT_SUCCESS,
            'message': 'Email sent successfully',
            'to': to_email,
            'subject': subject,
            'from': from_email,
            'attachments': attached_files,
            'message_id': message_id,
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': round(elapsed, 2)
        }
    except smtplib.SMTPAuthenticationError as e:
        return {
            'status': 'error',
            'code': EXIT_SEND_ERROR,
            'message': f'Authentication failed: {str(e)}',
            'to': to_email,
            'timestamp': datetime.now().isoformat()
        }
    except smtplib.SMTPException as e:
        return {
            'status': 'error',
            'code': EXIT_SEND_ERROR,
            'message': f'SMTP error: {str(e)}',
            'to': to_email,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'status': 'error',
            'code': EXIT_SEND_ERROR,
            'message': str(e),
            'to': to_email,
            'timestamp': datetime.now().isoformat()
        }


def send_batch(recipients, smtp_config, email_config, json_mode=False):
    """
    Send email to multiple recipients

    Args:
        recipients: List of email addresses or dicts with 'email' key
        smtp_config: Dict with SMTP settings
        email_config: Dict with email content (subject, text, html, attachments)

    Returns: dict with batch results
    """
    results = []
    success_count = 0
    failed_count = 0

    for i, recipient in enumerate(recipients, 1):
        # Extract email from dict or use string directly
        if isinstance(recipient, dict):
            to_email = recipient.get('email') or recipient.get('to')
        else:
            to_email = recipient.strip()

        if not to_email:
            continue

        if not json_mode:
            print(f"Sending {i}/{len(recipients)}: {to_email}...", file=sys.stderr)

        result = send_email(
            smtp_host=smtp_config['smtp_host'],
            smtp_port=smtp_config['smtp_port'],
            from_email=smtp_config['from_email'],
            to_email=to_email,
            subject=email_config['subject'],
            text=email_config.get('text'),
            html=email_config.get('html'),
            attachments=email_config.get('attachments'),
            use_tls=smtp_config['use_tls'],
            username=smtp_config.get('username'),
            password=smtp_config.get('password')
        )

        results.append(result)

        if result['status'] == 'success':
            success_count += 1
        else:
            failed_count += 1

        # Small delay between emails to avoid rate limiting
        if i < len(recipients):
            time.sleep(0.5)

    return {
        'status': 'batch',
        'code': EXIT_SUCCESS if failed_count == 0 else EXIT_SEND_ERROR,
        'total': len(recipients),
        'success': success_count,
        'failed': failed_count,
        'details': results,
        'timestamp': datetime.now().isoformat()
    }


def load_recipients_from_file(file_path, category_filter=None):
    """
    Load recipients from CSV or text file

    Formats supported:
    - Plain text: one email per line
    - CSV: with 'email' or 'to' column, optionally 'categories' or 'tags' column

    CSV with categories example:
      email,categories
      admin@example.com,"Notfall,Error,Ausfall"
      dev@example.com,"Error,Info"
      monitor@example.com,"Info,Erfolg"

    Args:
        file_path: Path to file
        category_filter: List of categories to filter by (e.g. ['Notfall', 'Error'])

    Returns: (recipients, error)
    """
    recipients = []
    file_path = Path(file_path)

    if not file_path.exists():
        return None, f"File not found: {file_path}"

    try:
        # Try CSV first
        with open(file_path, 'r') as f:
            # Peek at first line
            first_line = f.readline().strip()
            f.seek(0)

            # Check if it looks like CSV
            if ',' in first_line or '\t' in first_line:
                reader = csv.DictReader(f)
                for row in reader:
                    # Look for email column (case insensitive)
                    email = None
                    for key in row.keys():
                        if key.lower() in ['email', 'to', 'e-mail', 'mail']:
                            email = row[key]
                            break

                    if not email or not email.strip():
                        continue

                    email = email.strip()

                    # Check categories if filter is provided
                    if category_filter:
                        # Look for categories/tags column
                        categories_str = None
                        for key in row.keys():
                            if key.lower() in ['categories', 'tags', 'category', 'tag', 'type']:
                                categories_str = row[key]
                                break

                        if categories_str:
                            # Parse categories (comma or semicolon separated)
                            categories = [c.strip() for c in categories_str.replace(';', ',').split(',')]

                            # Check if any filter category matches
                            if any(cat in categories for cat in category_filter):
                                recipients.append(email)
                        # If no categories column but filter is set, skip this recipient
                    else:
                        # No filter, add all
                        recipients.append(email)

            else:
                # Plain text - one email per line
                # Category filtering not supported for plain text
                if category_filter:
                    return None, "Category filtering requires CSV format with 'categories' column"

                f.seek(0)
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '@' in line:
                        recipients.append(line)

        return recipients, None
    except Exception as e:
        return None, str(e)


def show_config():
    """Show current configuration"""
    print("=" * 60)
    print("   Current Email Configuration")
    print("=" * 60)
    print()

    if not CONFIG_FILE.exists():
        print("No configuration file found.")
        print(f"Expected location: {CONFIG_FILE}")
        print()
        print("Run './send_email.py setup' to configure")
        return

    config = load_config()
    if not config:
        print("Configuration file is empty or invalid")
        return

    print(f"Config file: {CONFIG_FILE}")
    print()
    print(f"SMTP Host:        {config.get('smtp_host', 'Not set')}")
    print(f"SMTP Port:        {config.get('smtp_port', 'Not set')}")
    print(f"Use TLS:          {config.get('smtp_tls', 'Not set')}")
    print(f"SMTP User:        {config.get('smtp_user', 'Not set')}")
    print(f"SMTP Password:    {'***' if config.get('smtp_pass') else 'Not set'}")
    print(f"From Email:       {config.get('smtp_from', 'Not set')}")
    print(f"Default To:       {config.get('default_to', 'Not set')}")
    print()
    print(f"IMAP Host:        {config.get('imap_host', 'Not set')}")
    print(f"IMAP Port:        {config.get('imap_port', 'Not set')}")
    print(f"IMAP SSL:         {config.get('imap_ssl', 'Not set')}")
    print()


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

def _decode_mime_words(s):
    """Decode an RFC2047-encoded header value to a plain string."""
    if s is None:
        return ""
    parts = []
    for raw, charset in decode_header(s):
        if isinstance(raw, bytes):
            parts.append(raw.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(raw)
    return "".join(parts)


def _get_text_body(msg):
    """Extract the plain-text body from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        # Fallback: try HTML part
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if ct == "text/html" and "attachment" not in cd:
                payload = part.get_content_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        return ""


def _parse_since(since_str):
    """
    Parse a --since value into a datetime (UTC-aware).

    Supported formats:
      - "today"          – midnight today (local time → UTC)
      - "Nh" / "Nm"     – N hours / minutes ago
      - "Nd"            – N days ago
      - ISO date         – e.g. "2026-03-10"
    """
    now = datetime.now(tz=timezone.utc)
    s = since_str.strip().lower()

    if s == "today":
        local_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Convert to UTC-aware
        offset = datetime.now().astimezone().utcoffset()
        return local_midnight.replace(tzinfo=timezone.utc) - (offset or timedelta(0))

    import re
    m = re.fullmatch(r'(\d+)(h|m|d)', s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit == 'h':
            return now - timedelta(hours=n)
        elif unit == 'm':
            return now - timedelta(minutes=n)
        elif unit == 'd':
            return now - timedelta(days=n)

    # Try ISO date
    try:
        dt = datetime.strptime(since_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    raise ValueError(f"Cannot parse --since value: {since_str!r}. "
                     "Use: 'today', '1h', '30m', '2d', or 'YYYY-MM-DD'")


def _connect_imap(config):
    """Open and authenticate an IMAP connection. Returns imap object."""
    imap_host = config.get("imap_host")
    imap_port = int(config.get("imap_port", 993))
    imap_ssl = config.get("imap_ssl", True)
    username = config.get("smtp_user")
    password = config.get("smtp_pass")

    if not imap_host:
        raise ValueError("imap_host not set in config. Run 'setup' or edit .email_config.json.")
    if not username or not password:
        raise ValueError("IMAP credentials missing (uses smtp_user / smtp_pass from config).")

    if imap_ssl:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port)
    else:
        imap = imaplib.IMAP4(imap_host, imap_port)

    imap.login(username, password)
    return imap


def _msg_to_dict(uid, raw_msg, flags):
    """Parse a raw RFC822 message bytes into a result dict."""
    msg = email_module.message_from_bytes(raw_msg)

    sender = _decode_mime_words(msg.get("From", ""))
    subject = _decode_mime_words(msg.get("Subject", ""))
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", "").strip()
    body = _get_text_body(msg)
    is_unread = b"\\Seen" not in flags

    return {
        "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
        "message_id": message_id,
        "from": sender,
        "subject": subject,
        "date": date_str,
        "unread": is_unread,
        "body": body,
    }


def cmd_check(args, config):
    """
    Connect via IMAP, list emails from INBOX.

    Filters: --from, --since
    Output: human-readable or --json
    """
    try:
        imap = _connect_imap(config)
    except Exception as e:
        result = {
            "status": "error",
            "code": EXIT_CONFIG_ERROR,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        output_result(result, args.json)
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        imap.select("INBOX", readonly=True)

        # Build IMAP search criteria
        criteria = []

        if hasattr(args, 'unread_only') and args.unread_only:
            criteria.append("UNSEEN")

        if hasattr(args, 'from_filter') and args.from_filter:
            criteria.append(f'FROM "{args.from_filter}"')

        if hasattr(args, 'since') and args.since:
            since_dt = _parse_since(args.since)
            # IMAP SINCE uses DD-Mon-YYYY format (server-side date, not time)
            imap_date = since_dt.strftime("%d-%b-%Y")
            criteria.append(f'SINCE {imap_date}')

        search_str = " ".join(criteria) if criteria else "ALL"

        typ, data = imap.uid("SEARCH", None, search_str)
        if typ != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {data}")

        uid_list = data[0].split() if data[0] else []

        emails = []
        for uid in uid_list:
            typ2, msg_data = imap.uid("FETCH", uid, "(FLAGS RFC822)")
            if typ2 != "OK" or not msg_data or msg_data[0] is None:
                continue

            # msg_data is [(b'... FLAGS (\\Seen)', b'raw...'), b')']
            flags = b""
            raw_bytes = None
            for part in msg_data:
                if isinstance(part, tuple):
                    header_info = part[0]
                    raw_bytes = part[1]
                    # Extract FLAGS from header_info
                    import re as _re
                    m = _re.search(rb'FLAGS \(([^)]*)\)', header_info)
                    if m:
                        flags = m.group(1)

            if raw_bytes is None:
                continue

            record = _msg_to_dict(uid, raw_bytes, flags)
            emails.append(record)

        imap.logout()

        # Client-side since filtering (for sub-day precision the IMAP SINCE
        # criterion only goes to day granularity)
        if hasattr(args, 'since') and args.since:
            since_dt = _parse_since(args.since)
            filtered = []
            for em in emails:
                try:
                    from email.utils import parsedate_to_datetime
                    msg_dt = parsedate_to_datetime(em["date"])
                    # Make timezone-aware if naive
                    if msg_dt.tzinfo is None:
                        msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    if msg_dt >= since_dt:
                        filtered.append(em)
                except Exception:
                    filtered.append(em)  # include if date unparseable
            emails = filtered

        result = {
            "status": "success",
            "code": EXIT_SUCCESS,
            "count": len(emails),
            "emails": emails,
            "timestamp": datetime.now().isoformat(),
        }

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if not emails:
                print("No emails found.")
            else:
                print(f"Found {len(emails)} email(s):\n")
                for i, em in enumerate(emails, 1):
                    status_marker = "[UNREAD]" if em["unread"] else "[read]"
                    print(f"  {i}. {status_marker} {em['from']}")
                    print(f"     Subject : {em['subject']}")
                    print(f"     Date    : {em['date']}")
                    print(f"     UID     : {em['uid']}")
                    preview = em["body"].strip().replace("\n", " ")[:120]
                    if preview:
                        print(f"     Preview : {preview}...")
                    print()

        sys.exit(EXIT_SUCCESS)

    except Exception as e:
        try:
            imap.logout()
        except Exception:
            pass
        result = {
            "status": "error",
            "code": EXIT_SEND_ERROR,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        output_result(result, args.json)
        sys.exit(EXIT_SEND_ERROR)


def cmd_read(args, config):
    """
    Fetch a single email by UID, display full body, mark as read.
    """
    try:
        imap = _connect_imap(config)
    except Exception as e:
        result = {
            "status": "error",
            "code": EXIT_CONFIG_ERROR,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        output_result(result, args.json)
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        # Open INBOX in read-write mode so we can mark as Seen
        imap.select("INBOX", readonly=False)

        uid = args.id.encode() if isinstance(args.id, str) else args.id

        typ, msg_data = imap.uid("FETCH", uid, "(FLAGS RFC822)")
        if typ != "OK" or not msg_data or msg_data[0] is None:
            raise RuntimeError(f"Message UID {args.id} not found.")

        flags = b""
        raw_bytes = None
        for part in msg_data:
            if isinstance(part, tuple):
                header_info = part[0]
                raw_bytes = part[1]
                import re as _re
                m = _re.search(rb'FLAGS \(([^)]*)\)', header_info)
                if m:
                    flags = m.group(1)

        if raw_bytes is None:
            raise RuntimeError(f"Could not fetch body for UID {args.id}.")

        record = _msg_to_dict(uid, raw_bytes, flags)

        # Mark as read
        imap.uid("STORE", uid, "+FLAGS", "\\Seen")
        record["unread"] = False

        imap.logout()

        if args.json:
            print(json.dumps({"status": "success", "code": EXIT_SUCCESS, **record,
                              "timestamp": datetime.now().isoformat()}, indent=2))
        else:
            print("=" * 60)
            print(f"From   : {record['from']}")
            print(f"Subject: {record['subject']}")
            print(f"Date   : {record['date']}")
            print(f"UID    : {record['uid']}")
            print("=" * 60)
            print()
            print(record["body"])

        sys.exit(EXIT_SUCCESS)

    except Exception as e:
        try:
            imap.logout()
        except Exception:
            pass
        result = {
            "status": "error",
            "code": EXIT_SEND_ERROR,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        output_result(result, args.json)
        sys.exit(EXIT_SEND_ERROR)


def cmd_wait(args, config):
    """
    Wait for a new email using IMAP IDLE (push, no polling).

    Connects to IMAP, selects INBOX, sends IDLE, and blocks on the
    socket until the server signals a new message or --timeout expires.
    When a new email arrives it is fetched and printed (optionally
    filtered by --from).  Exits with "NO_NEW_EMAIL" if the timeout
    fires without a matching message.
    """
    EXIT_TIMEOUT = 5   # local-only exit code for this command

    try:
        imap = _connect_imap(config)
    except Exception as e:
        result = {
            "status": "error",
            "code": EXIT_CONFIG_ERROR,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        output_result(result, args.json)
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        # Check IDLE capability
        typ, caps_data = imap.capability()
        caps = b" ".join(caps_data).upper() if caps_data else b""
        if b"IDLE" not in caps:
            raise RuntimeError(
                "IMAP server does not advertise IDLE capability. "
                "Cannot use push-mode wait."
            )

        imap.select("INBOX", readonly=False)

        # --- Send raw IDLE command ----------------------------------------
        # imaplib assigns a tag internally; we build our own so we can
        # recognise the tagged OK/NO response that ends the IDLE session.
        tag = b"IDLE001"
        imap.send(tag + b" IDLE\r\n")

        # Server must respond with a continuation line ("+ idling" or similar)
        # before it will push untagged EXISTS notifications.
        continuation = imap.readline()
        if not continuation.startswith(b"+"):
            raise RuntimeError(
                f"IMAP server did not accept IDLE (response: {continuation!r})"
            )

        # --- Wait for server push -----------------------------------------
        sock = imap.socket()
        timeout = getattr(args, "timeout", 300)
        deadline = time.monotonic() + timeout

        found_uid = None
        buf = b""

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            readable, _, _ = _select.select([sock], [], [], min(remaining, 30))

            if not readable:
                # No data yet; send a NOOP-style keepalive by re-reading
                # remaining time and looping (IDLE is still active).
                continue

            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk

            # Look for untagged EXISTS (new message notification).
            # Format: "* <n> EXISTS\r\n"
            import re as _re
            if _re.search(rb'\* \d+ EXISTS', buf):
                found_uid = True   # flag; actual UID resolved below
                break

        # --- End IDLE session ---------------------------------------------
        imap.send(b"DONE\r\n")
        # Drain the tagged response (IDLE001 OK ...)
        while True:
            line = imap.readline()
            if line.startswith(tag):
                break
            if not line:
                break

        if not found_uid:
            imap.logout()
            msg = "NO_NEW_EMAIL"
            if args.json:
                print(json.dumps({
                    "status": "timeout",
                    "code": EXIT_TIMEOUT,
                    "message": msg,
                    "timestamp": datetime.now().isoformat(),
                }, indent=2))
            else:
                print(msg)
            sys.exit(EXIT_TIMEOUT)

        # --- Find the newest unseen message(s) ----------------------------
        # After IDLE signals EXISTS we search for UNSEEN messages so we
        # fetch only the genuinely new ones.
        search_criteria = ["UNSEEN"]
        if hasattr(args, "from_filter") and args.from_filter:
            search_criteria.append(f'FROM "{args.from_filter}"')

        search_str = " ".join(search_criteria)
        typ, data = imap.uid("SEARCH", None, search_str)
        if typ != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {data}")

        uid_list = data[0].split() if data[0] else []

        if not uid_list:
            # EXISTS arrived but no UNSEEN message matches the --from filter.
            imap.logout()
            msg = "NO_NEW_EMAIL"
            if args.json:
                print(json.dumps({
                    "status": "timeout",
                    "code": EXIT_TIMEOUT,
                    "message": msg,
                    "timestamp": datetime.now().isoformat(),
                }, indent=2))
            else:
                print(msg)
            sys.exit(EXIT_TIMEOUT)

        # Take the latest (last) matching UID
        uid = uid_list[-1]

        typ2, msg_data = imap.uid("FETCH", uid, "(FLAGS RFC822)")
        if typ2 != "OK" or not msg_data or msg_data[0] is None:
            raise RuntimeError(f"Could not fetch message UID {uid!r}.")

        flags = b""
        raw_bytes = None
        for part in msg_data:
            if isinstance(part, tuple):
                header_info = part[0]
                raw_bytes = part[1]
                import re as _re2
                m = _re2.search(rb'FLAGS \(([^)]*)\)', header_info)
                if m:
                    flags = m.group(1)

        if raw_bytes is None:
            raise RuntimeError(f"Empty body for UID {uid!r}.")

        record = _msg_to_dict(uid, raw_bytes, flags)

        # Mark as read
        imap.uid("STORE", uid, "+FLAGS", "\\Seen")
        record["unread"] = False

        imap.logout()

        if args.json:
            print(json.dumps({
                "status": "success",
                "code": EXIT_SUCCESS,
                **record,
                "timestamp": datetime.now().isoformat(),
            }, indent=2))
        else:
            print("=" * 60)
            print(f"From   : {record['from']}")
            print(f"Subject: {record['subject']}")
            print(f"Date   : {record['date']}")
            print(f"UID    : {record['uid']}")
            print("=" * 60)
            print()
            print(record["body"])

        sys.exit(EXIT_SUCCESS)

    except Exception as e:
        try:
            imap.send(b"DONE\r\n")
        except Exception:
            pass
        try:
            imap.logout()
        except Exception:
            pass
        result = {
            "status": "error",
            "code": EXIT_SEND_ERROR,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        output_result(result, args.json)
        sys.exit(EXIT_SEND_ERROR)


def main():
    # Check for special commands first
    if len(sys.argv) > 1:
        if sys.argv[1] == 'setup':
            return 0 if setup_config() else 1
        elif sys.argv[1] == 'show-config':
            show_config()
            return 0
        elif sys.argv[1] == 'check':
            config = load_config()
            p = argparse.ArgumentParser(
                prog=f"{sys.argv[0]} check",
                description="Check INBOX for emails via IMAP",
            )
            p.add_argument("--from", dest="from_filter", metavar="ADDRESS",
                           help="Filter by sender address")
            p.add_argument("--since", metavar="TIMESPEC",
                           help="Show emails since: 'today', '1h', '30m', '2d', 'YYYY-MM-DD'")
            p.add_argument("--unread", dest="unread_only", action="store_true",
                           help="Only show unread emails")
            p.add_argument("--json", action="store_true",
                           help="Output as JSON")
            check_args = p.parse_args(sys.argv[2:])
            cmd_check(check_args, config)
            return 0
        elif sys.argv[1] == 'read':
            config = load_config()
            p = argparse.ArgumentParser(
                prog=f"{sys.argv[0]} read",
                description="Read a specific email by UID and mark it as read",
            )
            p.add_argument("id", help="Message UID (from 'check' output)")
            p.add_argument("--json", action="store_true",
                           help="Output as JSON")
            read_args = p.parse_args(sys.argv[2:])
            cmd_read(read_args, config)
            return 0
        elif sys.argv[1] == 'wait':
            config = load_config()
            p = argparse.ArgumentParser(
                prog=f"{sys.argv[0]} wait",
                description="Wait for a new email via IMAP IDLE (push, not polling)",
            )
            p.add_argument("--from", dest="from_filter", metavar="ADDRESS",
                           help="Only match emails from this sender address")
            p.add_argument("--timeout", type=int, default=300, metavar="SECONDS",
                           help="Max seconds to wait (default: 300)")
            p.add_argument("--json", action="store_true",
                           help="Output as JSON")
            wait_args = p.parse_args(sys.argv[2:])
            cmd_wait(wait_args, config)
            return 0

    parser = argparse.ArgumentParser(
        description="Send emails via SMTP / read emails via IMAP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Special commands:
  %(prog)s setup                          Interactive configuration wizard
  %(prog)s show-config                    Show current configuration
  %(prog)s check [--from ADDR] [--since SPEC] [--unread] [--json]
  %(prog)s read <uid> [--json]
  %(prog)s wait [--from ADDR] [--timeout N] [--json]

Send examples:
  # Gmail (requires app password)
  %(prog)s --smtp smtp.gmail.com --port 587 --tls \\
           -u your@gmail.com -p app-password \\
           -f your@gmail.com -t recipient@example.com \\
           -s "Subject" -m "Message"

  # With attachment
  %(prog)s -t recipient@example.com -s "Subject" -m "Message" -a file.pdf

  # Local mail server (no auth)
  %(prog)s --smtp localhost --port 25 \\
           -f sender@localhost -t recipient@example.com \\
           -s "Subject" -m "Message"

Check/read/wait examples:
  %(prog)s check --json
  %(prog)s check --since 1h --json
  %(prog)s check --from boss@example.com --since today
  %(prog)s check --unread
  %(prog)s read 12345 --json
  %(prog)s wait --json
  %(prog)s wait --from boss@example.com --timeout 60 --json

Environment variables:
  SMTP_HOST       SMTP server hostname
  SMTP_PORT       SMTP port
  SMTP_USER       SMTP username
  SMTP_PASS       SMTP password
  SMTP_FROM       Default sender email
  SMTP_TLS        Use TLS (1 or true)
"""
    )

    # Email parameters
    parser.add_argument("-f", "--from-email", help="Sender email address")
    parser.add_argument("-t", "--to", help="Recipient email address")
    parser.add_argument("-s", "--subject", help="Email subject")
    parser.add_argument("--batch", help="Send to multiple recipients from file (CSV or text)")
    parser.add_argument("--category", action="append", help="Filter recipients by category (CSV only, can be used multiple times)")
    parser.add_argument("-m", "--message", help="Email message (plain text)")
    parser.add_argument("--text-file", help="Read text message from file")
    parser.add_argument("--html", help="HTML message body")
    parser.add_argument("--html-file", help="Read HTML message from file")
    parser.add_argument("-a", "--attachment", action="append", help="Attach file (can be used multiple times)")

    # SMTP configuration
    parser.add_argument("--smtp", help="SMTP server (default: from env or localhost)")
    parser.add_argument("--port", type=int, help="SMTP port (default: 587 with TLS, 25 without)")
    parser.add_argument("--tls", action="store_true", help="Use TLS encryption")
    parser.add_argument("-u", "--username", help="SMTP username")
    parser.add_argument("-p", "--password", help="SMTP password")

    # Options
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    # Load config file (needed early for default_to)
    config = load_config()

    # Fall back to default_to from config
    if not args.to and not args.batch and config.get("default_to"):
        args.to = config["default_to"]

    # Validate required args
    if not args.batch and not args.to:
        parser.error("Either -t/--to or --batch is required")

    if not args.subject:
        parser.error("-s/--subject is required")

    # Get configuration with priority: CLI args > env vars > config file > defaults
    smtp_host = args.smtp or os.getenv("SMTP_HOST") or config.get("smtp_host", "localhost")

    # TLS handling
    if args.tls:
        use_tls = True
    elif os.getenv("SMTP_TLS"):
        use_tls = os.getenv("SMTP_TLS", "").lower() in ['1', 'true', 'yes']
    elif "smtp_tls" in config:
        use_tls = config.get("smtp_tls", False)
    else:
        use_tls = False

    # Port with smart default
    if args.port:
        smtp_port = args.port
    elif os.getenv("SMTP_PORT"):
        smtp_port = int(os.getenv("SMTP_PORT"))
    elif "smtp_port" in config:
        smtp_port = config.get("smtp_port", 587)
    else:
        smtp_port = 587 if use_tls else 25

    username = args.username or os.getenv("SMTP_USER") or config.get("smtp_user")
    password = args.password or os.getenv("SMTP_PASS") or config.get("smtp_pass")
    from_email = args.from_email or os.getenv("SMTP_FROM") or config.get("smtp_from")

    if not from_email:
        result = {
            'status': 'error',
            'code': EXIT_CONFIG_ERROR,
            'message': 'Sender email not set (use -f or env SMTP_FROM or setup config)',
            'timestamp': datetime.now().isoformat()
        }
        output_result(result, args.json)
        sys.exit(EXIT_CONFIG_ERROR)

    # Get message body
    text_body = None
    html_body = None

    if args.message:
        text_body = args.message
    elif args.text_file:
        try:
            with open(args.text_file, 'r') as f:
                text_body = f.read()
        except Exception as e:
            result = {
                'status': 'error',
                'code': EXIT_FILE_ERROR,
                'message': f'Error reading file {args.text_file}: {e}',
                'timestamp': datetime.now().isoformat()
            }
            output_result(result, args.json)
            sys.exit(EXIT_FILE_ERROR)

    if args.html:
        html_body = args.html
    elif args.html_file:
        try:
            with open(args.html_file, 'r') as f:
                html_body = f.read()
        except Exception as e:
            result = {
                'status': 'error',
                'code': EXIT_FILE_ERROR,
                'message': f'Error reading HTML file {args.html_file}: {e}',
                'timestamp': datetime.now().isoformat()
            }
            output_result(result, args.json)
            sys.exit(EXIT_FILE_ERROR)

    if not text_body and not html_body:
        result = {
            'status': 'error',
            'code': EXIT_CONFIG_ERROR,
            'message': 'No message body provided (use -m, --text-file, --html, or --html-file)',
            'timestamp': datetime.now().isoformat()
        }
        output_result(result, args.json)
        sys.exit(EXIT_CONFIG_ERROR)

    # Verbose output (only if not JSON mode)
    if args.verbose and not args.json:
        print(f"SMTP Server: {smtp_host}:{smtp_port}", file=sys.stderr)
        print(f"TLS: {use_tls}", file=sys.stderr)
        print(f"Auth: {'Yes' if username else 'No'}", file=sys.stderr)
        print(f"From: {from_email}", file=sys.stderr)
        if args.batch:
            print(f"Batch mode: {args.batch}", file=sys.stderr)
        else:
            print(f"To: {args.to}", file=sys.stderr)
        print(f"Subject: {args.subject}", file=sys.stderr)
        if args.attachment:
            print(f"Attachments: {', '.join(args.attachment)}", file=sys.stderr)
        print(file=sys.stderr)

    # Prepare SMTP and email config
    smtp_config = {
        'smtp_host': smtp_host,
        'smtp_port': smtp_port,
        'from_email': from_email,
        'use_tls': use_tls,
        'username': username,
        'password': password
    }

    email_config = {
        'subject': args.subject,
        'text': text_body,
        'html': html_body,
        'attachments': args.attachment
    }

    # Send email(s)
    if args.batch:
        # Batch send
        recipients, error = load_recipients_from_file(args.batch, args.category)
        if error:
            result = {
                'status': 'error',
                'code': EXIT_FILE_ERROR,
                'message': f'Failed to load recipients: {error}',
                'timestamp': datetime.now().isoformat()
            }
            output_result(result, args.json)
            sys.exit(EXIT_FILE_ERROR)

        if not recipients:
            result = {
                'status': 'error',
                'code': EXIT_FILE_ERROR,
                'message': 'No valid recipients found in batch file',
                'timestamp': datetime.now().isoformat()
            }
            output_result(result, args.json)
            sys.exit(EXIT_FILE_ERROR)

        result = send_batch(recipients, smtp_config, email_config, args.json)
        output_result(result, args.json)
        sys.exit(result['code'])

    else:
        # Single send
        result = send_email(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            from_email=from_email,
            to_email=args.to,
            subject=args.subject,
            text=text_body,
            html=html_body,
            attachments=args.attachment,
            use_tls=use_tls,
            username=username,
            password=password
        )

        output_result(result, args.json)
        sys.exit(result['code'])


if __name__ == "__main__":
    main()
