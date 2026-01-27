#!/usr/bin/env python3
"""
Simple Email Sender
Supports SMTP with or without authentication
"""

import smtplib
import argparse
import sys
import os
import json
import csv
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


CONFIG_FILE = Path.home() / ".email_config.json"

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
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        # Set permissions to 600 (only user can read/write)
        CONFIG_FILE.chmod(0o600)
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
    print(f"  {CONFIG_FILE}")
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
    elif choice == "2":
        config["smtp_host"] = "smtp-mail.outlook.com"
        config["smtp_port"] = 587
        config["smtp_tls"] = True
    elif choice == "3":
        config["smtp_host"] = "smtp.strato.de"
        config["smtp_port"] = 587
        config["smtp_tls"] = True
    else:
        config["smtp_host"] = input("SMTP Host: ").strip()
        config["smtp_port"] = int(input("SMTP Port (default: 587): ").strip() or "587")
        tls = input("Use TLS? [Y/n]: ").strip().lower()
        config["smtp_tls"] = tls != 'n'

    print()
    config["smtp_user"] = input("SMTP Username/Email: ").strip()
    config["smtp_pass"] = input("SMTP Password: ").strip()
    config["smtp_from"] = input(f"From Email (default: {config['smtp_user']}): ").strip() or config["smtp_user"]

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
    print(f"SMTP Host:     {config.get('smtp_host', 'Not set')}")
    print(f"SMTP Port:     {config.get('smtp_port', 'Not set')}")
    print(f"Use TLS:       {config.get('smtp_tls', 'Not set')}")
    print(f"SMTP User:     {config.get('smtp_user', 'Not set')}")
    print(f"SMTP Password: {'***' if config.get('smtp_pass') else 'Not set'}")
    print(f"From Email:    {config.get('smtp_from', 'Not set')}")
    print()


def main():
    # Check for special commands first
    if len(sys.argv) > 1:
        if sys.argv[1] == 'setup':
            return 0 if setup_config() else 1
        elif sys.argv[1] == 'show-config':
            show_config()
            return 0

    parser = argparse.ArgumentParser(
        description="Send emails via SMTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Setup:
  %(prog)s setup          Interactive configuration wizard

Examples:
  # Gmail (requires app password)
  %(prog)s --smtp smtp.gmail.com --port 587 --tls \\
           -u your@gmail.com -p app-password \\
           -f your@gmail.com -t recipient@example.com \\
           -s "Subject" -m "Message"

  # Outlook/Hotmail
  %(prog)s --smtp smtp-mail.outlook.com --port 587 --tls \\
           -u your@outlook.com -p password \\
           -f your@outlook.com -t recipient@example.com \\
           -s "Subject" -m "Message"

  # With attachment
  %(prog)s --smtp smtp.gmail.com --port 587 --tls \\
           -u your@gmail.com -p password \\
           -f your@gmail.com -t recipient@example.com \\
           -s "Subject" -m "Message" -a file.pdf

  # Local mail server (no auth)
  %(prog)s --smtp localhost --port 25 \\
           -f sender@localhost -t recipient@example.com \\
           -s "Subject" -m "Message"

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

    # Validate required args
    if not args.batch and not args.to:
        parser.error("Either -t/--to or --batch is required")

    if not args.subject:
        parser.error("-s/--subject is required")

    # Load config file
    config = load_config()

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
