"""
Business Process Automation - simple base project
-------------------------------------------------
Automates 4 routine business tasks using only the Python standard library:
  1. Invoice generation      (orders.csv -> one invoice file per order)
  2. Sales report            (summary by customer + pending amount)
  3. Payment reminders       (emails for overdue orders; dry-run by default)
  4. File organizer          (sorts a folder into subfolders by file type)
Every action is recorded in an SQLite audit log.

Run:  python business_process_automation.py
"""

import csv
import os
import shutil
import smtplib
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "output"
ORDERS_FILE = DATA_DIR / "orders.csv"
DB_FILE = DATA_DIR / "bpa.db"
GST_RATE = 0.18  # 18% tax

# Optional SMTP settings (set as environment variables to send real emails)
SMTP_HOST = os.getenv("SMTP_HOST")          # e.g. smtp.gmail.com
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


# ---------------------------------------------------------------- setup ----
def setup():
    DATA_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_FILE) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT, action TEXT, details TEXT)""")
    if not ORDERS_FILE.exists():
        create_sample_data()


def create_sample_data():
    today = date.today()
    rows = [
        ("1001", "Asha Traders", "asha@example.com", "Laptop", 2, 55000, today - timedelta(days=10), "Pending"),
        ("1002", "Ravi Stores", "ravi@example.com", "Printer", 1, 12000, today + timedelta(days=5), "Pending"),
        ("1003", "Asha Traders", "asha@example.com", "Mouse", 10, 500, today - timedelta(days=30), "Paid"),
        ("1004", "Meera Tech", "meera@example.com", "Monitor", 3, 9000, today - timedelta(days=3), "Pending"),
        ("1005", "Ravi Stores", "ravi@example.com", "Keyboard", 5, 1200, today - timedelta(days=15), "Paid"),
    ]
    with open(ORDERS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["order_id", "customer", "email", "item", "qty",
                    "unit_price", "due_date", "status"])
        w.writerows(rows)
    print(f"Sample data created: {ORDERS_FILE}")


def log(action, details=""):
    with sqlite3.connect(DB_FILE) as db:
        db.execute("INSERT INTO audit_log (timestamp, action, details) VALUES (?,?,?)",
                   (datetime.now().isoformat(timespec="seconds"), action, details))


def load_orders():
    with open(ORDERS_FILE, newline="", encoding="utf-8") as f:
        orders = list(csv.DictReader(f))
    for o in orders:
        o["qty"] = int(o["qty"])
        o["unit_price"] = float(o["unit_price"])
        o["due_date"] = date.fromisoformat(o["due_date"])
        o["subtotal"] = o["qty"] * o["unit_price"]
        o["tax"] = round(o["subtotal"] * GST_RATE, 2)
        o["total"] = o["subtotal"] + o["tax"]
    return orders


# ---------------------------------------------------- 1. invoice generation ----
def generate_invoices():
    folder = OUT_DIR / "invoices"
    folder.mkdir(exist_ok=True)
    orders = load_orders()
    for o in orders:
        text = f"""\
==================== INVOICE ====================
Invoice No : INV-{o['order_id']}
Date       : {date.today()}
Due Date   : {o['due_date']}
Status     : {o['status']}

Bill To    : {o['customer']} <{o['email']}>
-------------------------------------------------
Item       : {o['item']}
Quantity   : {o['qty']}
Unit Price : {o['unit_price']:,.2f}
-------------------------------------------------
Subtotal   : {o['subtotal']:,.2f}
GST (18%)  : {o['tax']:,.2f}
TOTAL      : {o['total']:,.2f}
=================================================
"""
        (folder / f"INV-{o['order_id']}.txt").write_text(text, encoding="utf-8")
    log("generate_invoices", f"{len(orders)} invoices")
    print(f"{len(orders)} invoices saved in {folder}")


# ---------------------------------------------------------- 2. sales report ----
def sales_report():
    orders = load_orders()
    by_customer = defaultdict(float)
    paid = pending = 0.0
    for o in orders:
        by_customer[o["customer"]] += o["total"]
        if o["status"].lower() == "paid":
            paid += o["total"]
        else:
            pending += o["total"]

    lines = [f"SALES REPORT - {date.today()}", "=" * 40]
    for cust, amt in sorted(by_customer.items(), key=lambda x: -x[1]):
        lines.append(f"{cust:<20}{amt:>15,.2f}")
    lines += ["-" * 40,
              f"{'Total Sales':<20}{paid + pending:>15,.2f}",
              f"{'Received (Paid)':<20}{paid:>15,.2f}",
              f"{'Pending':<20}{pending:>15,.2f}"]
    report = "\n".join(lines)
    (OUT_DIR / "sales_report.txt").write_text(report, encoding="utf-8")
    log("sales_report", f"total={paid + pending:.2f}")
    print(report)


# ------------------------------------------------------ 3. payment reminders ----
def send_email(to, subject, body):
    """Send via SMTP if configured, otherwise write to a log file (dry run)."""
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = SMTP_USER, to, subject
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return "sent"
    with open(OUT_DIR / "email_log.txt", "a", encoding="utf-8") as f:
        f.write(f"To: {to}\nSubject: {subject}\n{body}\n{'-' * 40}\n")
    return "dry-run"


def payment_reminders():
    overdue = [o for o in load_orders()
               if o["status"].lower() != "paid" and o["due_date"] < date.today()]
    if not overdue:
        print("No overdue payments.")
        return
    for o in overdue:
        days = (date.today() - o["due_date"]).days
        body = (f"Dear {o['customer']},\n\nInvoice INV-{o['order_id']} for "
                f"{o['total']:,.2f} was due on {o['due_date']} ({days} days overdue). "
                f"Please arrange payment at the earliest.\n\nRegards,\nAccounts Team")
        mode = send_email(o["email"], f"Payment Reminder: INV-{o['order_id']}", body)
        print(f"Reminder for INV-{o['order_id']} -> {o['email']} [{mode}]")
        log("payment_reminder", f"INV-{o['order_id']} {mode}")


# ------------------------------------------------------- 4. file organizer ----
FILE_TYPES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".pptx"],
    "Spreadsheets": [".xls", ".xlsx", ".csv"],
    "Archives": [".zip", ".rar", ".7z"],
}


def organize_folder():
    path = input("Folder path to organize: ").strip().strip('"')
    folder = Path(path)
    if not folder.is_dir():
        print("Folder not found.")
        return
    moved = 0
    for item in folder.iterdir():
        if not item.is_file():
            continue
        category = next((c for c, exts in FILE_TYPES.items()
                         if item.suffix.lower() in exts), "Others")
        target = folder / category
        target.mkdir(exist_ok=True)
        shutil.move(str(item), str(target / item.name))
        moved += 1
    log("organize_folder", f"{moved} files in {folder}")
    print(f"{moved} files organized.")


# ------------------------------------------------------------------ menu ----
def show_audit_log():
    with sqlite3.connect(DB_FILE) as db:
        for row in db.execute("SELECT timestamp, action, details FROM audit_log "
                              "ORDER BY id DESC LIMIT 15"):
            print(" | ".join(str(x) for x in row))


def run_all():
    generate_invoices()
    print()
    sales_report()
    print()
    payment_reminders()


MENU = {
    "1": ("Generate invoices", generate_invoices),
    "2": ("Sales report", sales_report),
    "3": ("Send payment reminders", payment_reminders),
    "4": ("Organize a folder", organize_folder),
    "5": ("Run all (1-3)", run_all),
    "6": ("View audit log", show_audit_log),
    "0": ("Exit", None),
}


def main():
    setup()
    while True:
        print("\n=== BUSINESS PROCESS AUTOMATION ===")
        for key, (label, _) in MENU.items():
            print(f"{key}. {label}")
        choice = input("Choose: ").strip()
        if choice == "0":
            print("Goodbye!")
            break
        if choice in MENU:
            print()
            MENU[choice][1]()
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
