# Business Process Automation

A simple Python project (standard library only) that automates:
1. Invoice generation (with 18% GST)
2. Sales report
3. Payment reminders (dry-run unless SMTP is configured)
4. File organizer
All actions are saved in an SQLite audit log.

## Run
    python business_process_automation.py

Requires Python 3.8+. Sample data (data/orders.csv) is created on first run.

## Optional: send real emails
Set these environment variables before running:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
