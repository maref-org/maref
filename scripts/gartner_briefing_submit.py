#!/usr/bin/env python3
"""Semi-automated Gartner Vendor Briefing form filler using Playwright.

This script:
1. Opens the Gartner registration/login page
2. Auto-fills form fields from gartner_briefing_data.json
3. Waits for human to complete CAPTCHA
4. Allows human review before submission

Usage:
    python3 scripts/gartner_briefing_submit.py --dry-run     # Preview only, no browser
    python3 scripts/gartner_briefing_submit.py --auto-fill    # Open browser and auto-fill
    python3 scripts/gartner_briefing_submit.py --auto-fill --data scripts/gartner_briefing_data.json

Requires: playwright (pip install playwright && playwright install chromium)
"""

from __future__ import annotations

import json
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

DATA_FILE = "scripts/gartner_briefing_data.json"
LOGIN_URL = "https://www.gartner.com/account/signin?method=initialize&TARGET=http%3A%2F%2Fwww.gartner.com%2Fanalyst%2Fvendor-briefing"
REGISTRATION_URL = "https://www.gartner.com/en/user/create?targetURL=https://www.gartner.com/analyst/vendor-briefing"
BRIEFING_FORM_URL = "http://www.gartner.com/analyst/vendor-briefing"


def load_data(path: str) -> dict:
    """Load briefing data from JSON file."""
    data_file = Path(path)
    if not data_file.exists():
        print(f"Error: Data file not found: {data_file}")
        print(f"Run: cp scripts/gartner_briefing_data.json.example {path}")
        sys.exit(1)
    return json.loads(data_file.read_text())


def dry_run(data: dict) -> None:
    """Print a preview of all fields to be filled."""
    print("=" * 80)
    print("Gartner Vendor Briefing — Dry Run Preview")
    print("=" * 80)
    print(f"\nRegistration URL: {REGISTRATION_URL}")
    print(f"Briefing Form URL: {BRIEFING_FORM_URL}")

    print("\n--- Fields to fill ---")
    for key, value in data.items():
        print(f"  {key:25s} = {value}")

    print("\n--- Execution Steps ---")
    print("  1. Open registration URL in browser")
    print("  2. Complete registration (including CAPTCHA)")
    print("  3. Login with new account")
    print("  4. Navigate to Vendor Briefing form")
    print("  5. Auto-fill all fields")
    print("  6. WAIT for human review")
    print("  7. Human clicks Submit")

    print("\n--- Warnings ---")
    print("  ⚠️  Do NOT auto-submit without human review")
    print("  ⚠️  CAPTCHA must be completed manually")
    print("  ⚠️  Registration URL may change — verify before running")

    print("\n" + "=" * 80)


def auto_fill_browser(data: dict, headless: bool = False) -> None:
    """Open browser and auto-fill the form (with human review)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: playwright not installed")
        print("Install: pip install playwright && playwright install chromium")
        sys.exit(1)

    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=500)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # Step 1: Open registration page
        print(f"Step 1: Opening registration page...")
        page.goto(REGISTRATION_URL, wait_until="networkidle", timeout=30000)
        print(f"  Current URL: {page.url}")
        print("  ⏸️  Please complete registration manually (including CAPTCHA)")
        print("  ⏸️  Press Enter when ready to continue...")
        input()

        # Step 2: Navigate to Vendor Briefing form
        print(f"Step 2: Opening Vendor Briefing form...")
        page.goto(BRIEFING_FORM_URL, wait_until="networkidle", timeout=30000)
        print(f"  Current URL: {page.url}")

        # Step 3: Try to auto-fill fields
        print("Step 3: Attempting to auto-fill form fields...")
        filled = 0
        skipped = 0

        # Common field selectors for Gartner forms
        field_selectors = {
            "company_name": ['input[name*="company" i]', 'input[name*="organization" i]', 'input[placeholder*="Company" i]'],
            "company_website": ['input[name*="website" i]', 'input[name*="url" i]', 'input[placeholder*="Website" i]'],
            "contact_name": ['input[name*="name" i]', 'input[name*="firstName" i]', 'input[name*="lastName" i]'],
            "contact_email": ['input[name*="email" i]', 'input[type="email"]'],
            "contact_title": ['input[name*="title" i]', 'input[name*="job" i]', 'input[name*="position" i]'],
            "contact_country": ['select[name*="country" i]', 'input[name*="country" i]'],
            "briefing_topic": ['input[name*="topic" i]', 'input[name*="subject" i]', 'textarea[name*="topic" i]'],
            "briefing_description": ['textarea', 'textarea[name*="description" i]', 'textarea[name*="message" i]'],
        }

        for key, value in data.items():
            if key in field_selectors:
                selectors = field_selectors[key]
                for selector in selectors:
                    try:
                        element = page.query_selector(selector)
                        if element and element.is_visible():
                            if element.evaluate("el => el.tagName") == "SELECT":
                                # For select elements, try to find matching option
                                print(f"  ⚠️  Select field detected: {key} (manual selection needed)")
                                skipped += 1
                            else:
                                element.click()
                                element.fill(str(value))
                                print(f"  ✅ Filled: {key}")
                                filled += 1
                            break
                    except Exception as e:
                        continue

        print(f"\n  Auto-filled: {filled} fields")
        if skipped > 0:
            print(f"  Skipped (manual): {skipped} fields")

        # Step 4: Wait for human review
        print("\n" + "=" * 60)
        print("FORM PRE-FILLED — Human Review Required")
        print("=" * 60)
        print("  1. Review all filled fields in the browser")
        print("  2. Manually fill any remaining fields")
        print("  3. Verify accuracy")
        print("  4. Press Enter when ready to submit, or Ctrl+C to abort")
        print("=" * 60)
        input("\n  Press Enter to continue (keep browser open), or Ctrl+C to abort...")

        print("\nBrowser will remain open. Please click Submit manually.")
        print("Close browser when done.")
        input("  Press Enter to close browser...")

        browser.close()
        print("Browser closed.")


def main() -> int:
    parser = ArgumentParser(description="Semi-automated Gartner Vendor Briefing form filler")
    parser.add_argument("--data", default=DATA_FILE, help="Briefing data JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no browser")
    parser.add_argument("--auto-fill", action="store_true", help="Open browser and auto-fill form")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (for testing only)")
    args = parser.parse_args()

    data = load_data(args.data)

    if args.dry_run:
        dry_run(data)
        return 0

    if args.auto_fill:
        auto_fill_browser(data, headless=args.headless)
        return 0

    # Default: dry run
    print("No action specified. Use --dry-run or --auto-fill")
    dry_run(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
