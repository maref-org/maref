from __future__ import annotations

import json
from html import escape as _escape_attr
from pathlib import Path
from string import Template

from maref.reporting.models import GovernanceReport

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table_rows(items: dict[str, int]) -> str:
    rows = []
    for key, val in sorted(items.items()):
        rows.append(f"<tr><td>{_esc(key)}</td><td>{val}</td></tr>")
    return "\n".join(rows)


class ReportExporter:
    def __init__(self, template_dir: str | Path | None = None) -> None:
        self._template_dir = Path(template_dir) if template_dir else _TEMPLATE_DIR

    def _load_template(self, name: str) -> Template:
        path = self._template_dir / name
        return Template(path.read_text("utf-8"))

    def export_report(
        self,
        report: GovernanceReport,
        output_path: str | Path,
    ) -> Path:
        tmpl = self._load_template("report.html")
        out = Path(output_path)

        time_start = ""
        if report.audit_summary.time_range_start is not None:
            time_start = str(report.audit_summary.time_range_start)
        time_end = ""
        if report.audit_summary.time_range_end is not None:
            time_end = str(report.audit_summary.time_range_end)

        merkle_display = report.merkle_root or "(empty \u2014 no events)"
        report_json_str = json.dumps(json.loads(report.to_json()), ensure_ascii=False)

        html = tmpl.safe_substitute(
            report_id=_esc(report.report_id),
            short_id=_esc(report.report_id[:8]),
            generated_at=_esc(report.created_at),
            report_version=_esc(report.report_version),
            generated_by=_esc(report.generated_by),
            signer_fingerprint=_esc(report.signer_fingerprint),
            total_events=str(report.audit_summary.total_events),
            time_start=_esc(time_start),
            time_end=_esc(time_end),
            event_type_rows=_table_rows(report.audit_summary.event_types),
            actor_rows=_table_rows(report.audit_summary.actor_counts),
            gov_state=_esc(report.system_state.governance_state or "\u2014"),
            active_agents=str(report.system_state.active_agents_count),
            sys_version=_esc(report.system_state.version or "\u2014"),
            merkle_root_display=_esc(merkle_display),
            report_json=report_json_str,
        )
        out.write_text(html, "utf-8")
        return out

    def export_index(
        self,
        report_dir: str | Path,
        output_path: str | Path,
        signer_fingerprint: str = "",
        public_key: str = "",
    ) -> Path:
        tmpl = self._load_template("index.html")
        out = Path(output_path)
        report_dir_path = Path(report_dir)

        reports: dict[str, GovernanceReport] = {}
        for f in sorted(report_dir_path.glob("*.json")):
            try:
                report = GovernanceReport.from_json(f.read_text("utf-8"))
            except Exception:
                continue
            # 同一份报告同时以 latest.json 和 report-<TS>.json 存在；排序后归档名在后，
            # 直接覆盖即保留归档副本，避免索引里出现重复行。
            reports[report.report_id] = report

        if reports:
            rows = ["<table><tr><th>Report ID</th><th>Date</th><th>Events</th><th>Status</th></tr>"]
            for r in reports.values():
                short = r.report_id[:8]
                date = r.created_at[:10] if r.created_at else "\u2014"
                status = "\u2705" if r.signature else "\u2014"
                rows.append(
                    f'<tr><td><a href="{short}.html">{_esc(short)}</a></td>'
                    f"<td>{_esc(date)}</td>"
                    f"<td>{r.audit_summary.total_events}</td>"
                    f"<td>{status}</td></tr>"
                )
            rows.append("</table>")
            table_html = "\n".join(rows)
        else:
            ls = sorted(report_dir_path.glob("*.*"))
            items = [f'<li><a href="{p.name}">{p.name}</a></li>' for p in ls if p.name != out.name]
            if items:
                table_html = f'<ul class="empty">{chr(10).join(items)}</ul>'
            else:
                table_html = '<p class="empty">No reports yet.</p>'

        fp = _esc(signer_fingerprint) if signer_fingerprint else "(not set)"
        verify_block = ""
        if signer_fingerprint:
            # 索引里链接的 fingerprint.txt 必须与索引同批落盘，否则线上是死链。
            out.parent.joinpath("fingerprint.txt").write_text(signer_fingerprint + "\n", "utf-8")
            verify_block = (
                '<p class="verify-link">Verify: <a href="fingerprint.txt">fingerprint.txt</a>'
            )
            if public_key:
                # 只在公钥确实随本次索引落盘时链接，避免又造一个死链。
                verify_block += (
                    f' · <a href="{_escape_attr(public_key, quote=True)}">public key</a>'
                )
            verify_block += "</p>"
        html = tmpl.safe_substitute(
            fingerprint=fp, report_table=table_html, verify_block=verify_block
        )
        out.write_text(html, "utf-8")
        return out
