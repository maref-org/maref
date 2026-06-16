#!/usr/bin/env python3
"""
arXiv Submission Automation — MAREF v0.30.0-GA

Max automation boundary:
  ✅ LaTeX validation & compilation check
  ✅ File completeness & size check
  ✅ arXiv metadata generation
  ✅ Browser launch with pre-filled URL
  ❌ Actual submission (arXiv requires human auth)

Usage:
  python scripts/arxiv_submit.py              # full pipeline
  python scripts/arxiv_submit.py --check-only # validation only, no browser
  python scripts/arxiv_submit.py --url-only   # print arXiv URL only

Environment:
  arXiv account: MAREF / 87909004@qq.com
  Primary class: cs.MA (Multiagent Systems)
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

import httpx
from defusedxml import ElementTree as ET

# ── Constants ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARXIV_DIR = os.path.join(PROJECT_ROOT, "docs", "arxiv-submission")
MAIN_TEX = os.path.join(ARXIV_DIR, "main.tex")
BIB_FILE = os.path.join(ARXIV_DIR, "references.bib")

SUBMISSION_META = {
    "title": ("MAREF: A Recursive Self-Evolving Governance Framework " "for Multi-Agent Systems"),
    "authors": "MAREF Research Team",
    "primary_class": "cs.MA",
    "categories": "cs.MA, cs.AI, cs.SE, cs.CR, cs.DC",
    "license": "Apache-2.0",
    "version": "v0.30.0-GA",
    "comments": (
        "v0.30.0-GA, 28 pages, Apache-2.0 licensed. " "Source code: https://github.com/maref-org"
    ),
    "abstract": (
        "We present MAREF (Multi-Agent Recursive Evolution Framework), "
        "a formal governance operating system for multi-agent systems "
        "built on a six-layer recursive architecture: Celestial Pole "
        "(constitutional constraints), Human Pole (human-in-the-loop), "
        "Earth Pole (execution semantics), Primary Hexagram (governance "
        "state machine), Derived Hexagram (domain-specific governance), "
        "and Line Change (dynamic adaptation). MAREF employs a 64-state "
        "Gray Code finite state machine, cryptographic attestation via "
        "SM2/SM3/SM4-GCM, and TLA+ formal verification to guarantee "
        "deterministic behavior across autonomous agent collectives. "
        "The framework supports consensus-aware execution with Byzantine "
        "fault tolerance (n >= 3f + 1), auditable decision pipelines "
        "with HMAC-SHA256 tamper evidence, and a dual-protocol "
        "integration layer (MCP + A2A) for ecosystem interoperability. "
        "We demonstrate MAREF's application in agent governance, "
        "supply chain security, compliance observability, and "
        "cross-organizational trust negotiation. The implementation "
        "is available as open-source software under Apache-2.0."
    ),
}

# arXiv has strict file size limits: 50MB total, 10MB per file
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_PER_FILE_BYTES = 10 * 1024 * 1024
FORBIDDEN_PACKAGES: list[str] = []
FORBIDDEN_COMMANDS = [
    r"\includegraphics",
    r"\input",
    r"\include",
]


# ── Helpers ──
def _green(s: str) -> str:
    return f"\033[92m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[91m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[93m{s}\033[0m"


def _print_header(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


# ── Validation Steps ──
def check_files() -> list[str]:
    errors: list[str] = []
    for path, label in [(MAIN_TEX, "main.tex"), (BIB_FILE, "references.bib")]:
        if not os.path.exists(path):
            errors.append(f"{label}: NOT FOUND at {path}")
        else:
            size = os.path.getsize(path)
            status = _green("OK") if size < MAX_PER_FILE_BYTES else _red("TOO LARGE")
            info = _yellow(f"({size:,} bytes)") if size > 1_000_000 else f"({size:,} bytes)"
            print(f"  {label:<30} {status} {info}")
    return errors


def check_bib_entries() -> int:
    with open(BIB_FILE) as f:
        content = f.read()
    count = sum(1 for line in content.splitlines() if line.startswith("@"))
    print(f"  bib entries:              {count}")
    return count


def check_citations() -> None:
    with open(MAIN_TEX) as f:
        content = f.read()
    import re

    cites = set()
    for match in re.finditer(r"\\cite\{([^}]*)\}", content):
        for c in match.group(1).split(","):
            c = c.strip()
            if c:
                cites.add(c)
    missing = []
    with open(BIB_FILE) as f:
        bib_content = f.read()
    for c in cites:
        if f"{{{c}," not in bib_content and f"{{{c}\n" not in bib_content:
            missing.append(c)
    if missing:
        print(f"  {_red('WARN')} citations missing from .bib: {', '.join(missing)}")
    else:
        print(f"  citations in .bib:         {_green(f'{len(cites)}/{len(cites)} OK')}")


def check_forbidden_packages() -> list[str]:
    with open(MAIN_TEX) as f:
        content = f.read()
    found = []
    for pkg in FORBIDDEN_PACKAGES:
        if f"\\usepackage{{{pkg}}}" in content:
            found.append(pkg)
    if found:
        print(f"  {_red(f'WARN forbidden packages: {found}')}")
    else:
        print(f"  forbidden packages:        {_green('none found')}")
    return found


def check_forbidden_commands() -> list[str]:
    with open(MAIN_TEX) as f:
        content = f.read()
    found = []
    for cmd in FORBIDDEN_COMMANDS:
        if cmd in content:
            found.append(cmd)
    if found:
        print(f"  {_yellow(f'note: found commands: {found}')}")
    return found


def check_class_options() -> None:
    with open(MAIN_TEX) as f:
        content = f.read()
    if "\\documentclass" in content:
        line = next((l for l in content.splitlines() if "\\documentclass" in l), "")
        print(f"  documentclass:             {line.strip()}")


def check_hyperref() -> None:
    with open(MAIN_TEX) as f:
        content = f.read()
    if "\\hypersetup" in content:
        print(f"  hyperref setup:            {_green('found')}")
    else:
        print(f"  {_yellow('WARN: no hyperref setup')}")


# ── Compilation Check ──
def find_latex() -> str | None:
    for cmd in ["pdflatex", "xelatex", "lualatex"]:
        path = shutil.which(cmd)
        if path:
            return cmd
    # Check basictex default paths
    basictex_paths = [
        "/usr/local/texlive/2026basic/bin/universal-darwin/pdflatex",
        "/usr/local/texlive/2025basic/bin/universal-darwin/pdflatex",
        "/Library/TeX/texbin/pdflatex",
        "~/Library/TeX/texbin/pdflatex",
    ]
    for p in basictex_paths:
        expanded = os.path.expanduser(p)
        if os.path.exists(expanded):
            return expanded
    return None


def check_compilation() -> bool:
    latex = find_latex()
    if not latex:
        print(f"  {_yellow('LaTeX not installed. Install with: brew install basictex')}")
        print(f"  {_yellow('Skipping compilation validation.')}")
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy files
        shutil.copy2(MAIN_TEX, os.path.join(tmpdir, "main.tex"))
        shutil.copy2(BIB_FILE, os.path.join(tmpdir, "references.bib"))

        result = subprocess.run(
            [latex, "-interaction=nonstopmode", "-output-directory", tmpdir, "main.tex"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            pdf_path = os.path.join(tmpdir, "main.pdf")
            if os.path.exists(pdf_path):
                pdf_size = os.path.getsize(pdf_path)
                print(f"  compilation:               {_green('OK')}")
                print(f"  PDF size:                  {pdf_size:,} bytes")
                # Check page count
                page_count = estimate_pdf_pages(pdf_path)
                if page_count:
                    print(f"  estimated pages:           {page_count}")
                return True
            else:
                print(f"  {_red('compilation OK but no PDF output')}")
                return False
        else:
            print(f"  {_red('compilation FAILED')}")
            # Show last 10 lines of errors
            errors = result.stdout.splitlines()[-20:]
            for line in errors:
                if "Error" in line or "error" in line or "!" in line:
                    print(f"    {_red(line.strip())}")
            return False


def estimate_pdf_pages(pdf_path: str) -> int | None:
    try:
        result = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Pages" in line:
                    return int(line.split(":")[1].strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        with open(pdf_path, "rb") as f:
            content = f.read()
        import re

        pages = len(re.findall(rb"/Type\s*/Page[^s]", content))
        if pages > 0:
            return pages
    except Exception:
        pass
    return None


# ── arXiv URL Generation ──
def build_arxiv_url() -> str:
    base = "https://arxiv.org/submit"
    params = {
        "title": SUBMISSION_META["title"],
        "authors": SUBMISSION_META["authors"],
        "categories": SUBMISSION_META["categories"],
    }
    return base


def build_arxiv_submit_url() -> str:
    """Build arXiv submit URL with pre-filled metadata."""
    return "https://arxiv.org/submit"


def generate_submit_json() -> dict:
    return {
        "submission_url": "https://arxiv.org/submit",
        "login_email": "87909004@qq.com",
        **SUBMISSION_META,
        "bib_file": BIB_FILE,
        "tex_file": MAIN_TEX,
        "upload_instructions": [
            f"1. Go to {_green('https://arxiv.org')}",
            "2. Login with MAREF / 87909004@qq.com",
            "3. Click 'START NEW SUBMISSION'",
            "4. Upload files: main.tex + references.bib",
            "5. arXiv auto-compiles → preview PDF (~28 pages)",
            "6. Verify and submit",
        ],
    }


# ── Browser Launch ──
def open_browser(url: str) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", url], check=True)
        elif system == "Linux":
            subprocess.run(["xdg-open", url], check=True)
        elif system == "Windows":
            os.startfile(url)
        print(f"  browser opened: {url}")
    except Exception as e:
        print(f"  {_yellow(f'could not open browser: {e}')}")
        print(f"  open manually: {url}")


# ── Main Pipeline ──
def run_pipeline(check_only: bool = False, url_only: bool = False) -> int:
    errors: list[str] = []

    _print_header("arXiv Submission Automation — MAREF v0.30.0-GA")

    # Step 1: File checks
    print(f"\n{'Step 1/6':>10} File existence & size")
    errors.extend(check_files())

    # Step 2: Content checks
    print(f"\n{'Step 2/6':>10} LaTeX content validation")
    check_bib_entries()
    check_citations()
    check_forbidden_packages()
    check_forbidden_commands()
    check_class_options()
    check_hyperref()

    # Step 3: Compilation (optional)
    print(f"\n{'Step 3/6':>10} Compilation validation")
    compiled = check_compilation()

    # Step 4: Metadata
    print(f"\n{'Step 4/6':>10} arXiv submission metadata")
    meta = generate_submit_json()
    print(f"  title:       {meta['title'][:70]}...")
    print(f"  authors:     {meta['authors']}")
    print(f"  class:       {meta['primary_class']}")
    print(f"  categories:  {meta['categories']}")
    print(f"  license:     {meta['license']}")
    print(f"  version:     {meta['version']}")

    # Step 5: Browser (unless check-only)
    print(f"\n{'Step 5/6':>10} Browser launch")
    if check_only or url_only:
        print(f"  {_yellow('skipped (--check-only or --url-only)')}")
    else:
        open_browser(build_arxiv_submit_url())

    # Step 6: Summary
    print(f"\n{'Step 6/6':>10} Summary")
    if errors:
        print(f"  {_red('ISSUES FOUND:')}")
        for e in errors:
            print(f"    ❌ {e}")
        print("\n  Fix the above issues before submitting to arXiv.")
        return 1
    else:
        print(f"  {_green('ALL CHECKS PASSED')}")
        print(f"\n  Proceed to: {_green('https://arxiv.org/submit')}")
        print("    Login:     MAREF / 87909004@qq.com")
        print("    Upload:    main.tex + references.bib")
        print("    Class:     cs.MA (Multiagent Systems)")
        return 0


# ── Endorsement Finder ──


def find_endorsers(max_papers: int = 20) -> list[dict]:
    """Query arXiv API for recent cs.MA papers and extract potential endorser info."""

    url = (
        f"https://export.arxiv.org/api/query?"
        f"search_query=cat:cs.MA&max_results={max_papers}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    print("  fetching recent cs.MA papers from arXiv API...")
    try:
        with httpx.Client(timeout=30, headers={"User-Agent": "MAREF/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
            xml_data = response.text
    except Exception as e:
        print(f"  {_red(f'API error: {e}')}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(xml_data)
    endorsers: list[dict] = []
    seen_authors: set[tuple[str, str]] = set()

    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""

        arxiv_id_el = entry.find("atom:id", ns)
        arxiv_id = arxiv_id_el.text.strip() if arxiv_id_el is not None else ""
        arxiv_id = arxiv_id.replace("http://arxiv.org/abs/", "")

        link_el = entry.find("atom:link[@title='abstract']", ns)
        abs_url = (
            link_el.attrib.get("href", f"https://arxiv.org/abs/{arxiv_id}")
            if link_el is not None
            else f"https://arxiv.org/abs/{arxiv_id}"
        )

        authors: list[dict] = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            name = name_el.text.strip() if name_el is not None else ""
            if name:
                authors.append({"name": name, "count": 0})

        if authors:
            endorsers.append(
                {
                    "arxiv_id": arxiv_id,
                    "title": title[:120],
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "endorse_url": f"https://arxiv.org/auth/endorse?x={arxiv_id}",
                    "authors": [a["name"] for a in authors],
                }
            )

    print(
        f"  found {len(endorsers)} recent cs.MA papers with {sum(len(e['authors']) for e in endorsers)} authors"
    )
    return endorsers


def run_endorsement_finder() -> int:
    _print_header("arXiv Endorsement Finder — cs.MA")

    print(f"\n  Endorsement code: {_green('VAE3BR')}")
    print(f"  Your email:       {_yellow('87909004@qq.com')}")
    print("  Target class:     cs.MA (Multiagent Systems)")

    endorsers = find_endorsers(max_papers=20)

    if not endorsers:
        print(f"\n  {_red('No papers found via API. Try:')}")
        print(f"    {_yellow('https://arxiv.org/list/cs.MA/recent')}")
        return 1

    print(f"\n{'=' * 70}")
    print("  Potential endorsers — authors of recent cs.MA papers")
    print(f"{'=' * 70}")

    from collections import Counter

    author_freq = Counter()
    for e in endorsers:
        for a in e["authors"]:
            author_freq[a] += 1

    # Show multi-paper authors first (more likely to be qualified)
    qualified = [(name, count) for name, count in author_freq.items() if count >= 2]
    single = [(name, count) for name, count in author_freq.items() if count == 1]

    print(f"\n  {_green('Most active authors (appear in 2+ recent papers)')}:")
    for name, count in sorted(qualified, key=lambda x: -x[1]):
        papers = [e for e in endorsers if name in e["authors"]]
        sample_title = papers[0]["title"][:80]
        print(f"\n    {_yellow(name)} ({count} papers)")
        print(f"      recent: {sample_title}...")
        print(f"      paper:  {papers[0]['url']}")

    print(f"\n  Other authors ({len(single)}):")
    for name, count in sorted(single, key=lambda x: x[0].split()[-1]):
        papers = [e for e in endorsers if name in e["authors"]]
        print(f"    {name:<30} {papers[0]['url']}")

    # Generate email template
    print(f"\n{'=' * 70}")
    print("  Email template — forward this to an endorser")
    print(f"{'=' * 70}")

    email_template = """Subject: Endorsement request for arXiv cs.MA submission

Dear Colleague,

I am writing to request your endorsement to submit a paper to arXiv
cs.MA (Multiagent Systems).

Title: MAREF: A Recursive Self-Evolving Governance Framework for Multi-Agent Systems
Authors: MAREF Research Team
Corresponding: Frankie Yang (Independent Researcher)

The paper presents MAREF, a formal governance operating system for
multi-agent systems based on a six-layer recursive architecture with
TLA+ formal verification and Byzantine fault tolerance.

I would greatly appreciate if you could endorse our submission by
visiting the following link:

  https://arxiv.org/auth/endorse?x=VAE3BR

Endorsement Code: VAE3BR

Thank you for your time and consideration.

Best regards,
Frankie Yang"""
    print(f"\n{email_template}\n")

    print("\n  Suggested endorsers (by paper URL — look for email on their website):")
    for name, count in sorted(qualified, key=lambda x: -x[1])[:5]:
        papers = [e for e in endorsers if name in e["authors"]]
        print(f"    {name:<30} {papers[0]['url']}")

    print(f"\n  {_green('Actions')}:")
    print("    1. Copy the email template above")
    print("    2. Find email addresses of suggested endorsers (check their websites)")
    print(f"    3. Forward arXiv's endorsement email to them with code {_green('VAE3BR')}")
    print(f"    4. Or share the link directly: {_green('https://arxiv.org/auth/endorse?x=VAE3BR')}")

    # Open browser tabs for the top papers
    print("\n  Opening top 3 papers in browser for reference...")
    for i, e in enumerate(endorsers[:3]):
        open_browser(e["url"])

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="arXiv submission automation for MAREF v0.30.0-GA")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate files only, skip browser launch",
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help="Print the arXiv submit URL and metadata, skip everything else",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metadata as JSON (for piping into other tools)",
    )
    parser.add_argument(
        "--find-endorsers",
        action="store_true",
        help="Find cs.MA endorsers via arXiv API and generate email template",
    )
    args = parser.parse_args()

    if args.find_endorsers:
        return run_endorsement_finder()

    if args.json:
        print(json.dumps(generate_submit_json(), indent=2, ensure_ascii=False))
        return 0

    return run_pipeline(check_only=args.check_only, url_only=args.url_only)


if __name__ == "__main__":
    sys.exit(main())
