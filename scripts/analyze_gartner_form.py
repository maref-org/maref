#!/usr/bin/env python3
"""Analyze Gartner Vendor Briefing form structure and prepare field mappings.

This script:
1. Fetches the Gartner registration/briefing form page
2. Parses all form fields (name, type, required status)
3. Maps them to gartner_briefing_data.json
4. Outputs a field-by-field filling guide

Usage:
    python3 scripts/analyze_gartner_form.py --url <URL>
    python3 scripts/analyze_gartner_form.py --login-page  # default Gartner login
    python3 scripts/analyze_gartner_form.py --data gartner_briefing_data.json
"""

from __future__ import annotations

import json
import re
import sys
from argparse import ArgumentParser
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_URL = "https://www.gartner.com/en/contact/vendor-briefings"
DATA_FILE = "scripts/gartner_briefing_data.json"


def fetch_page(url: str) -> str:
    """Fetch a web page and return HTML content."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_form_fields(html: str) -> list[dict[str, str]]:
    """Extract form fields from HTML using regex (lightweight, no dependencies)."""
    fields = []
    # Match input, select, textarea elements
    tag_pattern = r'<(input|select|textarea)\s+([^>]*)/?>'
    for match in re.finditer(tag_pattern, html, re.IGNORECASE | re.DOTALL):
        tag_type = match.group(1).lower()
        attrs_str = match.group(2)

        # Extract attributes
        name_match = re.search(r'name=["\']([^"\']*)["\']', attrs_str)
        id_match = re.search(r'id=["\']([^"\']*)["\']', attrs_str)
        type_match = re.search(r'type=["\']([^"\']*)["\']', attrs_str)
        placeholder_match = re.search(r'placeholder=["\']([^"\']*)["\']', attrs_str)
        required_match = re.search(r'required', attrs_str, re.IGNORECASE)

        if not name_match:
            continue

        name = name_match.group(1)
        if tag_type == "input":
            field_type = type_match.group(1).lower() if type_match else "text"
            if field_type in ("hidden", "submit", "button", "reset"):
                continue
        elif tag_type == "select":
            field_type = "select"
        elif tag_type == "textarea":
            field_type = "textarea"
        else:
            field_type = "text"

        fields.append({
            "name": name,
            "id": id_match.group(1) if id_match else "",
            "type": field_type,
            "placeholder": placeholder_match.group(1) if placeholder_match else "",
            "required": bool(required_match),
        })

    # Also check for labels
    label_pattern = r'<label[^>]*for=["\']([^"\']*)["\'][^>]*>(.*?)</label>'
    labels = {}
    for label_match in re.finditer(label_pattern, html, re.IGNORECASE | re.DOTALL):
        for_id = label_match.group(1)
        text = re.sub(r'<[^>]+>', '', label_match.group(2)).strip()
        if text:
            labels[for_id] = text

    # Attach labels to fields
    for field in fields:
        field_id = field.get("id", "")
        if field_id and field_id in labels:
            field["label"] = labels[field_id]

    return fields


def load_briefing_data(path: str) -> dict:
    """Load pre-filled briefing data from JSON."""
    data_file = Path(path)
    if not data_file.exists():
        print(f"Data file not found: {data_file}")
        print(f"Create it first or use --generate-data to create from template")
        return {}
    return json.loads(data_file.read_text())


def suggest_mapping(fields: list[dict], data: dict) -> list[dict]:
    """Suggest mappings between form fields and briefing data."""
    mappings = []
    data_keys = {k.lower(): k for k in data.keys()}

    field_to_key = {
        # Company fields
        "company": "company_name",
        "companyname": "company_name",
        "company_name": "company_name",
        "org": "company_name",
        "organization": "company_name",
        "companywebsite": "company_website",
        "company_website": "company_website",
        "website": "company_website",
        "url": "company_website",
        "companytype": "company_type",
        "company_type": "company_type",
        "type": "company_type",
        # Contact fields
        "contactname": "contact_name",
        "contact_name": "contact_name",
        "firstname": "contact_name",
        "lastname": "contact_name",
        "name": "contact_name",
        "fullname": "contact_name",
        "contactemail": "contact_email",
        "contact_email": "contact_email",
        "email": "contact_email",
        "mail": "contact_email",
        "contacttitle": "contact_title",
        "contact_title": "contact_title",
        "title": "contact_title",
        "jobtitle": "contact_title",
        "job_title": "contact_title",
        "position": "contact_title",
        "country": "contact_country",
        "phone": "contact_phone",
        "telephone": "contact_phone",
        "contactphone": "contact_phone",
        "contact_phone": "contact_phone",
        # Briefing fields
        "topic": "briefing_topic",
        "subject": "briefing_topic",
        "briefingtopic": "briefing_topic",
        "briefing_topic": "briefing_topic",
        "description": "briefing_description",
        "briefingdescription": "briefing_description",
        "briefing_description": "briefing_description",
        "message": "briefing_description",
        "comments": "briefing_description",
        "details": "briefing_description",
        "analyst": "target_analysts",
        "targetanalysts": "target_analysts",
        "target_analysts": "target_analysts",
        "competitors": "competitors",
        "businessvalue": "business_value",
        "business_value": "business_value",
        "value": "business_value",
    }

    for field in fields:
        name = field.get("name", "").lower()
        field_id = field.get("id", "").lower()
        label = field.get("label", "").lower()

        # Try matching against known mappings
        mapped_key = None
        for pattern, key in field_to_key.items():
            if pattern in name or pattern in field_id or pattern in label:
                if key in data_keys:
                    mapped_key = data_keys[key]
                    break

        field["mapped_to"] = mapped_key
        if mapped_key:
            field["suggested_value"] = data.get(mapped_key, "")[:50] + "..." if len(data.get(mapped_key, "")) > 50 else data.get(mapped_key, "")

        mappings.append(field)

    return mappings


def print_mapping_report(fields: list[dict], data: dict) -> None:
    """Print a formatted mapping report."""
    print("=" * 80)
    print("Gartner Vendor Briefing — Form Field Mapping Report")
    print("=" * 80)

    mapped = [f for f in fields if f.get("mapped_to")]
    unmapped = [f for f in fields if not f.get("mapped_to")]

    print(f"\nTotal fields found: {len(fields)}")
    print(f"Auto-mapped: {len(mapped)}")
    print(f"Unmapped (manual review needed): {len(unmapped)}")

    print("\n" + "-" * 80)
    print("AUTO-MAPPED FIELDS")
    print("-" * 80)
    for field in mapped:
        required = " [REQUIRED]" if field.get("required") else ""
        print(f"\n  Field: {field['name']} ({field['type']}){required}")
        print(f"  Label: {field.get('label', 'N/A')}")
        print(f"  Maps to: {field['mapped_to']}")
        print(f"  Value: {field.get('suggested_value', 'N/A')}")

    if unmapped:
        print("\n" + "-" * 80)
        print("UNMAPPED FIELDS — Manual review needed")
        print("-" * 80)
        for field in unmapped:
            required = " [REQUIRED]" if field.get("required") else ""
            print(f"\n  Field: {field['name']} ({field['type']}){required}")
            print(f"  Label: {field.get('label', 'N/A')}")
            print(f"  Placeholder: {field.get('placeholder', 'N/A')}")

    # Checklist
    print("\n" + "=" * 80)
    print("FILLING CHECKLIST")
    print("=" * 80)
    data_keys = set(data.keys())
    mapped_keys = {f["mapped_to"] for f in fields if f.get("mapped_to")}
    missing = data_keys - mapped_keys
    if missing:
        print("\nData keys NOT mapped to any form field:")
        for key in sorted(missing):
            print(f"  ⚠️  {key}: {data[key][:60]}...")
    else:
        print("\n✅ All data keys are mapped to form fields")

    print("\n" + "=" * 80)


def generate_data_template(path: str) -> None:
    """Generate a data template file."""
    template = {
        "company_name": "Your Company Name",
        "company_website": "https://your-website.com",
        "company_type": "Private / Public / Open Source",
        "product_name": "Your Product Name",
        "product_category": "Product Category",
        "contact_name": "Your Name",
        "contact_email": "your@email.com",
        "contact_title": "Your Title",
        "contact_country": "Your Country",
        "briefing_topic": "Briefing Topic / Title",
        "briefing_description": "Brief description of your product and why Gartner analysts should care.",
        "target_analysts": "Target analyst names (optional)",
        "competitors": "Main competitors",
        "business_value": "Key business value proposition",
    }
    Path(path).write_text(json.dumps(template, indent=2, ensure_ascii=False))
    print(f"Data template generated: {path}")
    print("Please edit the file with your actual information")


def main() -> int:
    parser = ArgumentParser(description="Analyze Gartner Vendor Briefing form and prepare field mappings")
    parser.add_argument("--url", default=DEFAULT_URL, help="Form URL to analyze")
    parser.add_argument("--data", default=DATA_FILE, help="Briefing data JSON file")
    parser.add_argument("--generate-data", action="store_true", help="Generate data template instead of analyzing")
    parser.add_argument("--output", default=None, help="Output mapping to JSON file")
    args = parser.parse_args()

    if args.generate_data:
        generate_data_template(args.data)
        return 0

    # Fetch and analyze
    print(f"Fetching: {args.url}")
    try:
        html = fetch_page(args.url)
    except Exception as e:
        print(f"Error fetching page: {e}")
        print("Note: Gartner pages may require JavaScript rendering.")
        print("Try using a browser to inspect the form manually.")
        return 1

    print(f"Fetched {len(html)} bytes of HTML")
    fields = extract_form_fields(html)
    print(f"Found {len(fields)} form fields")

    if not fields:
        print("No form fields detected. The form may be loaded dynamically via JavaScript.")
        print("Recommended: Use browser DevTools to inspect the form at:")
        print("  https://www.gartner.com/account/signin?method=initialize&TARGET=http%3A%2F%2Fwww.gartner.com%2Fanalyst%2Fvendor-briefing")
        return 1

    # Load data and suggest mappings
    data = load_briefing_data(args.data)
    if data:
        fields = suggest_mapping(fields, data)
        print_mapping_report(fields, data)
    else:
        print("\nNo data file found. Run with --generate-data first, then edit the file.")

    # Optionally save mapping
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(fields, indent=2, ensure_ascii=False))
        print(f"\nMapping saved to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
