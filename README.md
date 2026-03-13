# shellmail - für KI optimiert

Python-Script zum Versenden und Lesen von E-Mails via SMTP/IMAP mit JSON-Output und Batch-Support.

## Requirements

**Python:** 3.7+

**Dependencies:** Keine! Nutzt nur Python Standard Library:
- `smtplib` - SMTP client
- `imaplib` - IMAP client
- `email` - Email message handling
- `json` - JSON parsing/output
- `csv` - CSV file parsing
- `argparse` - CLI argument parsing
- `pathlib` - File path handling
- `re` - Email validation

## Installation

**1. Repository klonen:**
```bash
git clone https://github.com/kreasteve/shellmail.git
cd shellmail
```

**2. Ausführbar machen:**
```bash
chmod +x send_email.py
```

**3. Konfigurieren:**
```bash
./send_email.py setup
```

**4. Testen:**
```bash
./send_email.py -t your@email.com -s "Test" -m "Hello World"
```

**Optional - Globale Installation:**
```bash
# Symlink erstellen für systemweite Nutzung
sudo ln -s $(pwd)/send_email.py /usr/local/bin/shellmail

# Dann von überall:
shellmail -t user@example.com -s "Test" -m "Hello"
```

## Features

✅ **Versteckte Config** - Zugangsdaten sicher in `.email_config.json` (neben dem Script oder in `~/`)
✅ **JSON Output** - Strukturierte, parsbare Ausgaben für KI/Automation
✅ **Batch-Versand** - Mehrere Empfänger aus CSV/Text-Datei
✅ **Category-System** - Filter Empfänger nach Alert-Level (Notfall, Error, Info, etc.)
✅ **Email-Validierung** - Prüft Adressen vor dem Versand
✅ **Exit Codes** - Verschiedene Codes für verschiedene Fehlertypen
✅ **IMAP Empfang** - Postfach lesen, filtern nach Absender/Zeit, als gelesen markieren

## Schnellstart

**1. Einmalige Konfiguration:**

```bash
cd ~/email
./send_email.py setup
```

**2. E-Mail senden:**

```bash
./send_email.py -t empfaenger@example.com -s "Betreff" -m "Nachricht"
```

## JSON Output Mode (für KI/Automation)

**Einzelne E-Mail mit JSON:**

```bash
./send_email.py --json -t user@example.com -s "Test" -m "Hello"
```

**Output:**
```json
{
  "status": "success",
  "code": 0,
  "message": "Email sent successfully",
  "to": "user@example.com",
  "subject": "Test",
  "from": "mt@kreasteve.de",
  "attachments": [],
  "message_id": "",
  "timestamp": "2026-01-27T08:26:57.787158",
  "elapsed_seconds": 0.35
}
```

**Exit Codes:**
- `0` - Erfolg
- `1` - Konfigurationsfehler
- `2` - Versandfehler
- `3` - Validierungsfehler
- `4` - Dateifehler

## Batch-Versand

### Einfache Text-Datei

**recipients.txt:**
```
admin@example.com
dev@example.com
monitor@example.com
```

**Versenden:**
```bash
./send_email.py --batch recipients.txt -s "Maintenance" -m "Server wird gewartet"
```

### CSV mit Category-System (Alert-Level)

**alerts.csv:**
```csv
email,categories,name
admin@example.com,"Notfall,Error,Ausfall",Admin Team
developer@example.com,"Error,Info",Dev Team
monitor@example.com,"Info,Erfolg",Monitoring
oncall@example.com,"Notfall,Ausfall",On-Call Team
report@example.com,"Erfolg,Info",Report Team
```

**Beispiele:**

```bash
# Nur an "Notfall"-Empfänger senden
./send_email.py --batch alerts.csv --category "Notfall" \
  -s "NOTFALL: Server down" -m "Kritischer Ausfall!"

# An "Error" ODER "Info" senden
./send_email.py --batch alerts.csv --category "Error" --category "Info" \
  -s "Update" -m "Neues Update verfügbar"

# Alle Empfänger (keine Filter)
./send_email.py --batch alerts.csv -s "Newsletter" -m "Monatlicher Report"

# Mit JSON Output
./send_email.py --json --batch alerts.csv --category "Notfall" \
  -s "Alert" -m "Kritischer Fehler"
```

**Batch-JSON-Output:**
```json
{
  "status": "batch",
  "code": 0,
  "total": 2,
  "success": 2,
  "failed": 0,
  "details": [
    {
      "status": "success",
      "code": 0,
      "message": "Email sent successfully",
      "to": "admin@example.com",
      ...
    },
    {
      "status": "success",
      "code": 0,
      "message": "Email sent successfully",
      "to": "oncall@example.com",
      ...
    }
  ],
  "timestamp": "2026-01-27T09:04:16.373143"
}
```

## E-Mails lesen (IMAP)

### `check` - INBOX prüfen

```bash
# Alle Emails (JSON)
shellmail check --json

# Nur ungelesene
shellmail check --unread

# Von bestimmtem Absender
shellmail check --from boss@example.com

# Seit heute
shellmail check --since today

# Letzte Stunde
shellmail check --since 1h

# Letzte 30 Minuten
shellmail check --since 30m

# Letzte 2 Tage
shellmail check --since 2d

# Kombiniert
shellmail check --from boss@example.com --since today --json
```

**check JSON-Output:**
```json
{
  "status": "success",
  "code": 0,
  "count": 2,
  "emails": [
    {
      "uid": "42",
      "message_id": "<abc123@mail.example.com>",
      "from": "boss@example.com",
      "subject": "Weekly Report",
      "date": "Fri, 13 Mar 2026 10:00:00 +0100",
      "unread": true,
      "body": "Please review the attached..."
    }
  ],
  "timestamp": "2026-03-13T11:00:00.000000"
}
```

### `read` - Einzelne Email lesen

```bash
# Email mit UID lesen (UID kommt aus 'check' Output)
shellmail read 42

# Als JSON
shellmail read 42 --json
```

Die Email wird automatisch als gelesen markiert (`unread: false`).

**read JSON-Output:**
```json
{
  "status": "success",
  "code": 0,
  "uid": "42",
  "message_id": "<abc123@mail.example.com>",
  "from": "boss@example.com",
  "subject": "Weekly Report",
  "date": "Fri, 13 Mar 2026 10:00:00 +0100",
  "unread": false,
  "body": "Please review the attached...",
  "timestamp": "2026-03-13T11:00:00.000000"
}
```

### IMAP-Konfiguration

Das Script nutzt dieselben Zugangsdaten (`smtp_user` / `smtp_pass`) für IMAP. Nur IMAP-Host und Port müssen zusätzlich konfiguriert werden:

```json
{
  "smtp_host": "smtp.strato.de",
  "smtp_port": 587,
  "smtp_tls": true,
  "smtp_user": "deine@domain.de",
  "smtp_pass": "passwort",
  "smtp_from": "deine@domain.de",
  "imap_host": "imap.strato.de",
  "imap_port": 993,
  "imap_ssl": true
}
```

Beim `setup`-Wizard werden die IMAP-Einstellungen für Gmail, Outlook und Strato automatisch gesetzt.

### IMAP-Einstellungen für gängige Provider

| Provider | imap_host | imap_port | imap_ssl |
|---|---|---|---|
| Strato | imap.strato.de | 993 | true |
| Gmail | imap.gmail.com | 993 | true |
| Outlook | outlook.office365.com | 993 | true |

## Use Cases für KI/Automation

### 1. Alert-System

```bash
# Python-Script ruft Email-Tool auf
if error_level == "critical":
    subprocess.run([
        "./send_email.py", "--json",
        "--batch", "alerts.csv",
        "--category", "Notfall",
        "-s", f"CRITICAL: {error_msg}",
        "-m", error_details
    ])
    result = json.loads(output)
```

### 2. Monitoring mit JSON-Parsing

```bash
#!/bin/bash
RESULT=$(./send_email.py --json -t admin@example.com \
  -s "Test" -m "Hello" 2>&1)

STATUS=$(echo "$RESULT" | jq -r '.status')
CODE=$(echo "$RESULT" | jq -r '.code')

if [ "$STATUS" = "success" ]; then
    echo "Email sent successfully"
else
    echo "Failed with code $CODE"
    exit $CODE
fi
```

### 3. Batch mit Fehlerbehandlung

```bash
./send_email.py --json --batch users.csv -s "Update" -m "..." > result.json

# Parse Ergebnisse
SUCCESS=$(jq '.success' result.json)
FAILED=$(jq '.failed' result.json)

if [ "$FAILED" -gt 0 ]; then
    # Handle failures
    jq '.details[] | select(.status=="error")' result.json
fi
```

## Weitere Beispiele

**Mit Anhang:**
```bash
./send_email.py -t user@example.com -s "Report" \
  -m "Anbei der Report" -a report.pdf -a data.csv
```

**HTML-Email:**
```bash
./send_email.py -t user@example.com -s "Newsletter" \
  --html-file newsletter.html
```

**Nachricht aus Datei:**
```bash
./send_email.py -t user@example.com -s "Bericht" \
  --text-file nachricht.txt
```

**Verbose + JSON:**
```bash
./send_email.py --json -v -t user@example.com -s "Test" -m "Hello"
# Verbose geht nach stderr, JSON nach stdout
```

## Konfiguration

### Config-Datei

```bash
# Anzeigen
./send_email.py show-config

# Neu einrichten
./send_email.py setup

# Manuell bearbeiten (Pfad je nach Setup)
nano .email_config.json
# oder
nano ~/.email_config.json
```

**Format:**
```json
{
  "smtp_host": "smtp.strato.de",
  "smtp_port": 587,
  "smtp_tls": true,
  "smtp_user": "deine@domain.de",
  "smtp_pass": "passwort",
  "smtp_from": "deine@domain.de",
  "default_to": "empfaenger@example.com",
  "imap_host": "imap.strato.de",
  "imap_port": 993,
  "imap_ssl": true
}
```

**`default_to`** (optional): Standard-Empfänger, der verwendet wird wenn `-t` nicht angegeben ist.
Nützlich für Scripts, die immer an dieselbe Adresse senden.

```bash
# Mit default_to in der Config: kein -t nötig
./send_email.py -s "Alert" -m "Server down"
```

### Config-Datei Suche

Das Script sucht in dieser Reihenfolge nach der Config:

1. `.email_config.json` im gleichen Verzeichnis wie das Script
2. `~/.email_config.json` im Home-Verzeichnis

`setup` speichert immer in das Verzeichnis neben dem Script (Option 1).

### Priorität

1. **CLI-Parameter** (höchste)
2. **Umgebungsvariablen**
3. **Config-Datei** (`.email_config.json` neben Script oder `~/.email_config.json`)
4. **Defaults**

## SMTP-Provider

### Gmail
```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_tls": true,
  "smtp_user": "deine@gmail.com",
  "smtp_pass": "app-passwort",
  "smtp_from": "deine@gmail.com"
}
```

### Outlook
```json
{
  "smtp_host": "smtp-mail.outlook.com",
  "smtp_port": 587,
  "smtp_tls": true,
  "smtp_user": "deine@outlook.com",
  "smtp_pass": "passwort",
  "smtp_from": "deine@outlook.com"
}
```

### Strato
```json
{
  "smtp_host": "smtp.strato.de",
  "smtp_port": 587,
  "smtp_tls": true,
  "smtp_user": "deine@domain.de",
  "smtp_pass": "passwort",
  "smtp_from": "deine@domain.de"
}
```

## Alle Optionen

```
Spezial-Befehle:
  setup                     Interaktive Konfiguration
  show-config               Config anzeigen (SMTP + IMAP)
  check [Optionen]          INBOX lesen (IMAP)
  read <uid> [--json]       Email lesen + als gelesen markieren

check-Optionen:
  --from ADDRESS            Filter nach Absender
  --since TIMESPEC          Filter nach Zeit: 'today', '1h', '30m', '2d', 'YYYY-MM-DD'
  --unread                  Nur ungelesene
  --json                    JSON-Output

Email-Parameter (send):
  -f, --from-email          Absender-Adresse
  -t, --to                  Empfänger-Adresse
  -s, --subject             Betreff (erforderlich)
  -m, --message             Nachricht
  --text-file               Nachricht aus Datei
  --html                    HTML-Nachricht
  --html-file               HTML aus Datei
  -a, --attachment          Datei anhängen (mehrfach möglich)

Batch-Mode:
  --batch FILE              CSV oder Text-Datei mit Empfängern
  --category CAT            Filter nach Category (mehrfach möglich)

SMTP-Config (überschreibt ~/.email_config.json):
  --smtp                    SMTP-Server
  --port                    SMTP-Port
  --tls                     TLS verwenden
  -u, --username            SMTP-Username
  -p, --password            SMTP-Passwort

Output/Debug:
  --json                    JSON-Output (für Automation)
  -v, --verbose             Verbose (stderr)
  -h, --help                Hilfe
```

## CSV Format

**Pflichtfelder:**
- `email` (oder `to`, `mail`, `e-mail`)

**Optionale Felder:**
- `categories` (oder `tags`, `category`, `type`) - Komma-separiert
- `name` - Wird nicht verwendet, nur für Übersicht

**Beispiel:**
```csv
email,categories,name
admin@example.com,"Notfall,Error",Admin
dev@example.com,"Error,Info",Developer
monitor@example.com,"Info,Erfolg",Monitoring
```

## Tipps für KI/Automation

1. **Immer --json verwenden** für parsbare Ausgaben
2. **Exit Codes prüfen** für Fehlerbehandlung
3. **Batch-Mode nutzen** für mehrere Empfänger
4. **Categories** für verschiedene Alert-Level
5. **Verbose auf stderr** → JSON auf stdout bleibt sauber

**Beispiel-Script:**
```python
import subprocess
import json

result = subprocess.run([
    "./send_email.py", "--json",
    "--batch", "alerts.csv",
    "--category", "Notfall",
    "-s", "Alert",
    "-m", "Server down!"
], capture_output=True, text=True)

data = json.loads(result.stdout)

if data['status'] == 'batch':
    print(f"Sent to {data['success']}/{data['total']} recipients")

    for detail in data['details']:
        if detail['status'] == 'error':
            print(f"Failed: {detail['to']}: {detail['message']}")

sys.exit(result.returncode)
```

## Troubleshooting

**JSON-Parse-Fehler:**
```bash
# Verwende 2>&1 nicht, wenn du --json nutzt
# Richtig:
./send_email.py --json ... > result.json

# Falsch:
./send_email.py --json ... 2>&1 > result.json  # stderr vermischt sich
```

**Verbose mit JSON:**
```bash
# Verbose geht nach stderr, JSON nach stdout
./send_email.py --json -v ... 2>debug.log 1>result.json
```

**Category-Filter funktioniert nicht:**
- Prüfe CSV-Format (Header muss "categories", "tags", oder "category" heißen)
- Categories sind case-sensitive ("Notfall" ≠ "notfall")
- Mehrere Categories komma-separiert: "Cat1,Cat2"

**Exit Codes prüfen:**
```bash
./send_email.py --json -t test@example.com -s "Test" -m "Hello"
echo "Exit code: $?"
```
