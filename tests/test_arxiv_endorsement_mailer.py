from __future__ import annotations

import gzip
import importlib.util
import io
import tarfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "arxiv_endorsement_mailer.py"
spec = importlib.util.spec_from_file_location("arxiv_endorsement_mailer", SCRIPT)
mailer = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mailer)


def test_decode_mime_handles_unknown_8bit_encoding() -> None:
    assert mailer.decode_mime("=?unknown-8bit?q?hello?=") == "hello"


def test_parse_monitor_accounts_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_ACCOUNTS", "a@qq.com:imap.qq.com,b@hotmail.com:outlook.office365.com")

    accounts = mailer.parse_monitor_accounts()

    assert accounts == [
        {"username": "a@qq.com", "server": "imap.qq.com"},
        {"username": "b@hotmail.com", "server": "outlook.office365.com"},
    ]


def test_extract_emails_filters_placeholders_and_deduplicates() -> None:
    text = "contact a@uni.edu, b@example.com, a@uni.edu, name@domain.invalid, trovato@corporation.com, ok.name@lab.org"

    emails = mailer.extract_emails(text)

    assert emails == ["a@uni.edu", "ok.name@lab.org"]


def test_extract_text_from_eprint_tar_gz() -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        data = b"\\author{Researcher\\thanks{email: researcher@lab.edu}}"
        info = tarfile.TarInfo("main.tex")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    payload = gzip.compress(raw.getvalue())

    text = mailer.extract_text_from_eprint(payload)

    assert "researcher@lab.edu" in text


def test_discover_targets_from_recent_page_and_sources() -> None:
    recent_html = """
    <a href="/abs/2606.01828">arXiv:2606.01828</a>
    Title: Dynamic Trust-Aware Sparse Communication Topology
    Wanshuang Gou, Zihan Liu
    <a href="/abs/2606.01581">arXiv:2606.01581</a>
    Title: Agent System Operations: Categorization
    Zexin Wang, Changhua Pei
    """
    source_by_url = {
        "https://arxiv.org/list/cs.MA/recent": recent_html,
        "https://arxiv.org/html/2606.01828": "Zihan Liu <zihan.liu@university.edu>",
        "https://arxiv.org/e-print/2606.01828": b"",
        "https://arxiv.org/html/2606.01581": "",
        "https://arxiv.org/e-print/2606.01581": b"Changhua Pei (changhua.pei@lab.ac.cn)",
    }

    def fake_fetch(url: str) -> bytes:
        value = source_by_url.get(url, "")
        return value if isinstance(value, bytes) else value.encode()

    targets = mailer.discover_targets(limit=2, fetch=fake_fetch)

    assert targets == [
        {
            "name": "Zihan Liu",
            "email": "zihan.liu@university.edu",
            "topic": "Dynamic Trust-Aware Sparse Communication Topology",
        },
        {
            "name": "Changhua Pei",
            "email": "changhua.pei@lab.ac.cn",
            "topic": "Agent System Operations: Categorization",
        },
    ]
