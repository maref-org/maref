"""Annex IV Technical Documentation Exporter.

Transforms TechnicalDocumentation into regulatory submission formats:
- PDF_READY: HTML with print CSS for PDF generation
- DOCX_READY: structured XML (docx-compatible)
- REGULATORY_XML: EU-compatible metadata format
- JSON: machine-readable (delegates to TechnicalDocumentation)
"""

from __future__ import annotations

import json
from typing import Any

from maref.compliance.eu_ai_act_v2.technical_docs import TechnicalDocumentation


class AnnexIVExporter:
    """Export TechnicalDocumentation to regulatory submission formats."""

    def __init__(self, doc: TechnicalDocumentation) -> None:
        self.doc = doc
        self._data: dict[str, Any] | None = None

    def _ensure_data(self) -> dict[str, Any]:
        if self._data is None:
            self._data = self.doc.generate()
        return self._data

    def to_pdf_ready_html(self) -> str:
        """Render as print-optimised HTML for PDF conversion."""
        data = self._ensure_data()
        md = data["document_metadata"]
        si = data["system_information"]

        sections_html = ""
        section_titles = [
            ("section_1_general_description", "1. General Description"),
            ("section_2_development_methodology", "2. Development Methodology"),
            ("section_3_system_architecture", "3. System Architecture"),
            ("section_4_data_governance", "4. Data Governance"),
            ("section_5_human_oversight", "5. Human Oversight"),
            ("section_6_validation_and_testing", "6. Validation and Testing"),
            ("section_7_cybersecurity_measures", "7. Cybersecurity Measures"),
            ("section_8_risk_management_system", "8. Risk Management System"),
            ("section_9_post_market_monitoring", "9. Post-Market Monitoring"),
            (
                "section_10_accuracy_robustness_cybersecurity",
                "10. Accuracy, Robustness & Cybersecurity",
            ),
        ]
        for key, title in section_titles:
            section_data = data.get(key, {})
            sections_html += f"<h2>{title}</h2>\n"
            sections_html += self._dict_to_html(section_data)

        evidence_html = ""
        if "audit_evidence" in data:
            ae = data["audit_evidence"]
            evidence_html = f"""<h2>Audit Evidence (Merkle Anchor)</h2>
<p><strong>Merkle Root:</strong> <code>{ae['merkle_root']}</code></p>
"""
            if ae["evidence_ids"]:
                evidence_html += "<ul>\n"
                for eid in ae["evidence_ids"]:
                    evidence_html += f"  <li><code>{eid}</code></li>\n"
                evidence_html += "</ul>\n"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{md['title']}</title>
<style>
  @page {{ size: A4; margin: 2.5cm; }}
  body {{ font-family: 'Times New Roman', serif; font-size: 12pt; line-height: 1.6; color: #000; }}
  h1 {{ font-size: 18pt; text-align: center; margin-bottom: 0.5cm; }}
  h2 {{ font-size: 14pt; margin-top: 1cm; border-bottom: 1px solid #333; }}
  table {{ width: 100%; border-collapse: collapse; margin: 0.5cm 0; }}
  th, td {{ border: 1px solid #555; padding: 4px 8px; text-align: left; font-size: 10pt; }}
  th {{ background: #eee; }}
  code {{ font-family: 'Courier New', monospace; font-size: 10pt; background: #f5f5f5; padding: 1px 3px; }}
  .metadata {{ text-align: center; font-size: 10pt; color: #555; margin-bottom: 1cm; }}
  ul {{ margin-top: 0; }}
</style>
</head>
<body>
<h1>{md['title']}</h1>
<div class="metadata">
  <p><strong>Regulation:</strong> {md['regulation']}</p>
  <p><strong>Article:</strong> {md['article']} — {md['annex']}</p>
  <p><strong>Generated:</strong> {md['generated_at']} | <strong>Version:</strong> {md.get('doc_version', 1)}</p>
</div>

<h2>System Information</h2>
<table>
  <tr><th>Name</th><td>{si['system_name']}</td></tr>
  <tr><th>Version</th><td>{si['version']}</td></tr>
  <tr><th>Intended Purpose</th><td>{si['intended_purpose']}</td></tr>
  <tr><th>Deployer</th><td>{si['deployer']}</td></tr>
  <tr><th>Risk Classification</th><td>{si['risk_classification']}</td></tr>
</table>

{sections_html}
{evidence_html}
</body>
</html>"""

    def to_regulatory_xml(self) -> str:
        """Generate EU-regulatory-format XML (Annex IV structured)."""
        data = self._ensure_data()
        md = data["document_metadata"]
        si = data["system_information"]

        def _xml_val(key: str, val: Any) -> str:
            if isinstance(val, dict):
                inner = "".join(
                    f"  <{k}>{_xml_val(k, v)}</{k}>\n" for k, v in val.items()
                )
                return f"\n<{key}>\n{inner}</{key}>\n"
            if isinstance(val, list):
                items = "".join(
                    f"  <item>{_xml_val('item', v)}</item>\n" for v in val
                )
                return f"\n<{key}>\n{items}</{key}>\n"
            return str(val)

        sections_xml = ""
        for key in [k for k in data if k.startswith("section_")]:
            sections_xml += f"  {_xml_val(key, data[key])}"

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<technical_documentation xmlns="https://eur-lex.europa.eu/2024/1689/annex-iv">
  <document_metadata>
    <title>{md['title']}</title>
    <regulation>{md['regulation']}</regulation>
    <article>Art.11</article>
    <annex>Annex IV</annex>
    <generated_at>{md['generated_at']}</generated_at>
    <doc_version>{md.get('doc_version', 1)}</doc_version>
  </document_metadata>
  <system_information>
    <system_name>{si['system_name']}</system_name>
    <version>{si['version']}</version>
    <intended_purpose>{si['intended_purpose']}</intended_purpose>
    <deployer>{si['deployer']}</deployer>
    <risk_classification>{si['risk_classification']}</risk_classification>
  </system_information>
{sections_xml}
</technical_documentation>"""

    def to_docx_ready_xml(self) -> str:
        """Generate docx-compatible structured XML.

        This produces Word-style XML fragments that can be embedded
        into a .docx document for regulatory submission.
        """
        data = self._ensure_data()
        md = data["document_metadata"]

        paragraphs: list[str] = []

        def _add_heading(text: str, level: int = 1) -> None:
            paragraphs.append(
                f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/>'
                f"</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"
            )

        def _add_text(text: str) -> None:
            paragraphs.append(
                f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
            )

        def _dict_to_docx(d: dict[str, Any] | list[Any], indent: int = 0) -> None:
            if isinstance(d, list):
                for item in d:
                    if isinstance(item, (dict, list)):
                        _dict_to_docx(item, indent + 1)
                    else:
                        _add_text(f"{'  ' * indent}- {item}")
                return
            if not isinstance(d, dict):
                _add_text(f"{'  ' * indent}{d}")
                return
            for k, v in d.items():
                label = k.replace("_", " ").title()
                if isinstance(v, (dict, list)):
                    _add_text(f"{'  ' * indent}{label}:")
                    _dict_to_docx(v, indent + 1)
                else:
                    _add_text(f"{'  ' * indent}{label}: {v}")

        _add_heading(md["title"], 1)
        _add_text(f"Regulation: {md['regulation']}")
        _add_text(f"Article: {md['article']} — {md['annex']}")
        _add_text(f"Generated: {md['generated_at']}")

        si = data["system_information"]
        _add_heading("System Information", 2)
        _dict_to_docx(si)

        section_titles = {
            "section_1_general_description": "General Description",
            "section_2_development_methodology": "Development Methodology",
            "section_3_system_architecture": "System Architecture",
            "section_4_data_governance": "Data Governance",
            "section_5_human_oversight": "Human Oversight",
            "section_6_validation_and_testing": "Validation and Testing",
            "section_7_cybersecurity_measures": "Cybersecurity Measures",
            "section_8_risk_management_system": "Risk Management System",
            "section_9_post_market_monitoring": "Post-Market Monitoring",
            "section_10_accuracy_robustness_cybersecurity": "Accuracy, Robustness & Cybersecurity",
        }
        for key, title in section_titles.items():
            section_data = data.get(key, {})
            _add_heading(title, 2)
            _dict_to_docx(section_data)

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + "".join(paragraphs)
            + "</w:document>"
        )

    def export_multi_format(self) -> dict[str, str]:
        """Export all formats at once. Convenience for CLI/API."""
        return {
            "json": json.dumps(self._ensure_data(), indent=2),
            "markdown": self.doc.generate_markdown(),
            "pdf_ready_html": self.to_pdf_ready_html(),
            "regulatory_xml": self.to_regulatory_xml(),
            "docx_ready_xml": self.to_docx_ready_xml(),
        }

    @staticmethod
    def _dict_to_html(data: dict[str, Any] | list[Any], level: int = 0) -> str:
        html_parts: list[str] = []
        if isinstance(data, list):
            html_parts.append("<ul>\n")
            for item in data:
                if isinstance(item, (dict, list)):
                    html_parts.append(f"  <li>{AnnexIVExporter._dict_to_html(item, level + 1)}</li>\n")
                else:
                    html_parts.append(f"  <li>{item}</li>\n")
            html_parts.append("</ul>\n")
            return "".join(html_parts)
        if not isinstance(data, dict):
            return f"<p>{data}</p>\n"
        html_parts.append("<table>\n")
        for k, v in data.items():
            label = k.replace("_", " ").title()
            if isinstance(v, (dict, list)):
                html_parts.append(f"<tr><td colspan='2'><strong>{label}</strong></td></tr>\n")
                html_parts.append(f"<tr><td colspan='2'>{AnnexIVExporter._dict_to_html(v, level + 1)}</td></tr>\n")
            else:
                html_parts.append(f"<tr><th>{label}</th><td>{v}</td></tr>\n")
        html_parts.append("</table>\n")
        return "".join(html_parts)
