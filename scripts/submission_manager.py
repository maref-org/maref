#!/usr/bin/env python3
"""MAREF submission pipeline manager — track, prepare, and submit to venues."""

import csv
import os
import platform
import subprocess
import sys
import tempfile
import shutil
from datetime import datetime, date
from pathlib import Path

PIPELINE_CSV = Path(__file__).resolve().parent.parent / "docs" / "submission-pipeline" / "submission_pipeline.csv"
ARXIV_DIR = Path(__file__).resolve().parent.parent / "docs" / "arxiv-submission"
MAIN_TEX = ARXIV_DIR / "main.tex"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "submission-pipeline" / "versions"

def _green(s): return f"\033[92m{s}\033[0m"
def _yellow(s): return f"\033[93m{s}\033[0m"
def _red(s): return f"\033[91m{s}\033[0m"
def _blue(s): return f"\033[94m{s}\033[0m"

def load_pipeline():
    rows = []
    with open(PIPELINE_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def save_pipeline(rows):
    fieldnames = ["name","venue","type","deadline","lang","format","cost_note","status","submission_url","notes"]
    with open(PIPELINE_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def open_browser(url):
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", url], check=True)
        elif system == "Linux":
            subprocess.run(["xdg-open", url], check=True)
        elif system == "Windows":
            os.startfile(url)
        print(f"  browser: {url}")
    except Exception as e:
        print(f"  could not open browser: {e}")
        print(f"  open manually: {url}")

def print_timeline(rows):
    today = date.today()
    print(f"\n{'=' * 70}")
    print(f"  MAREF Submission Pipeline  —  {today}")
    print(f"{'=' * 70}")
    print(f"{'Venue':<40} {'Deadline':<12} {'Status':<12} {'Days Left':>10}")
    print(f"{'-'*40} {'-'*12} {'-'*12} {'-'*10}")
    for row in sorted(rows, key=lambda r: r["deadline"]):
        dl = datetime.strptime(row["deadline"], "%Y-%m-%d").date()
        days = (dl - today).days
        dl_str = row["deadline"]
        status = row["status"]
        if days < 0:
            dl_str = _red(dl_str)
            days_str = _red("OVERDUE")
        elif days <= 7:
            dl_str = _red(dl_str)
            days_str = _red(f"{days}d")
        elif days <= 14:
            dl_str = _yellow(dl_str)
            days_str = _yellow(f"{days}d")
        else:
            days_str = _green(f"{days}d")
        name_short = row["name"][:38]
        print(f"  {name_short:<40} {dl_str:<12} {status:<12} {days_str:>10}")

def cmd_status(rows):
    print_timeline(rows)
    return 0

def cmd_open(row):
    url = row["submission_url"]
    print(f"  Opening: {_blue(url)}")
    open_browser(url)

def cmd_prepare(row):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    name_slug = row["name"].lower().replace(" ", "_").replace("(", "").replace(")", "")
    lang = row["lang"]
    deadline = row["deadline"]
    print(f"\n  Preparing: {_green(row['name'])}")
    print(f"  Language:  {lang}")
    print(f"  Deadline:  {deadline}")
    print(f"  Template:  {row['format']}")
    print(f"\n  {_yellow('Manual steps required:')}")
    print(f"    1. Create {row['format']}-compliant LaTeX/Word file")
    print(f"    2. Adapt content to {lang} language style")
    print(f"    3. Include cover letter if required")
    print(f"    4. Submit via {row['submission_url']}")
    print(f"\n  Output dir: {OUTPUT_DIR / name_slug}/")

def cmd_list(rows):
    print_timeline(rows)
    print(f"\n  {_green(f'{len(rows)} venues in pipeline')}")

def cmd_mark(rows, name, new_status):
    for row in rows:
        if row["name"] == name:
            old_status = row["status"]
            row["status"] = new_status
            save_pipeline(rows)
            print(f"  {name}: {_yellow(old_status)} → {_green(new_status)}")
            return 0
    print(f"  {_red(f'venue not found: {name}')}")
    return 1

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MAREF submission pipeline manager")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show pipeline timeline")
    sub.add_parser("list", help="List all venues")

    open_p = sub.add_parser("open", help="Open venue submission portal in browser")
    open_p.add_argument("name", help="Venue name (partial match)")

    prepare_p = sub.add_parser("prepare", help="Show preparation info for a venue")
    prepare_p.add_argument("name", help="Venue name")

    mark_p = sub.add_parser("mark", help="Update venue status")
    mark_p.add_argument("name", help="Venue name")
    mark_p.add_argument("status", choices=["pending", "preparing", "submitted", "under_review", "accepted", "rejected"])

    args = parser.parse_args()
    rows = load_pipeline()

    if args.command == "status":
        return cmd_status(rows)
    elif args.command == "list":
        return cmd_list(rows)
    elif args.command == "open":
        matches = [r for r in rows if args.name.lower() in r["name"].lower()]
        if not matches:
            print(f"  {_red('no match')}")
            return 1
        if len(matches) > 1:
            print(f"  {_yellow('multiple matches, using first:')}")
        return cmd_open(matches[0])
    elif args.command == "prepare":
        matches = [r for r in rows if args.name.lower() in r["name"].lower()]
        if not matches:
            print(f"  {_red('no match')}")
            return 1
        return cmd_prepare(matches[0])
    elif args.command == "mark":
        return cmd_mark(rows, args.name, args.status)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
