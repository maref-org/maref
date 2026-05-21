from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DeployStage(str, Enum):
    MVP = "mvp"
    MIXED = "mixed"
    INTERNALIZATION = "internalization"
    UNKNOWN = "unknown"


_STAGE_KEYWORDS: dict[DeployStage, list[str]] = {
    DeployStage.MVP: ["mvp", "wool-mvp", "阶段一", "phase 1", "0-4周"],
    DeployStage.MIXED: ["混合期", "阶段二", "phase 2", "1-3个月"],
    DeployStage.INTERNALIZATION: ["内化期", "ip王国", "阶段三", "phase 3", "3-12个月"],
}


@dataclass
class TableRow:
    cells: list[str]
    section_heading: str

    def to_dict(self) -> dict[str, Any]:
        return {"cells": self.cells, "section": self.section_heading}


@dataclass
class CostModel:
    stage: str
    items: dict[str, float] = field(default_factory=dict)
    total: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "items": self.items, "total": self.total}


@dataclass
class ComplianceRule:
    rule_id: str
    description: str
    category: str  # daily / weekly / monthly / discipline
    is_automated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "category": self.category,
            "is_automated": self.is_automated,
        }


@dataclass
class Hypothesis:
    name: str
    method: str
    pass_threshold: str
    fail_criterion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "method": self.method,
            "pass_threshold": self.pass_threshold,
            "fail_criterion": self.fail_criterion,
        }


@dataclass
class DocumentSection:
    heading: str
    level: int
    content: str
    subsections: list[DocumentSection] = field(default_factory=list)
    milestones: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    table_rows: list[TableRow] = field(default_factory=list)
    checklists: list[str] = field(default_factory=list)

    def collect_all_reqs(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for r in self.requirements:
            if r not in seen:
                seen.add(r)
                result.append(r)
        for sub in self.subsections:
            for r in sub.collect_all_reqs():
                if r not in seen:
                    seen.add(r)
                    result.append(r)
        return result

    def collect_all_tables(self) -> list[TableRow]:
        rows = list(self.table_rows)
        for sub in self.subsections:
            rows.extend(sub.collect_all_tables())
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "heading": self.heading,
            "level": self.level,
            "content_preview": self.content[:200],
            "milestones": self.milestones,
            "requirements": self.requirements[:20],
            "table_rows": [r.to_dict() for r in self.table_rows[:10]],
            "checklists": self.checklists[:10],
            "subsections": [s.to_dict() for s in self.subsections],
        }


@dataclass
class FeatureDocument:
    title: str
    raw_path: str
    stages: dict[DeployStage, list[DocumentSection]] = field(default_factory=dict)
    all_sections: list[DocumentSection] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    compliance_rules: list[ComplianceRule] = field(default_factory=list)
    cost_models: list[CostModel] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_requirements(self) -> int:
        seen: set[str] = set()
        for sections in self.stages.values():
            for s in sections:
                for r in s.collect_all_reqs():
                    seen.add(r)
        return len(seen)

    @property
    def total_milestones(self) -> int:
        count = 0
        for sections in self.stages.values():
            for s in sections:
                count += len(s.milestones)
                for sub in s.subsections:
                    count += len(sub.milestones)
        return count

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "raw_path": self.raw_path,
            "stages": {
                k.value: [s.to_dict() for s in v]
                for k, v in self.stages.items()
            },
            "total_requirements": self.total_requirements,
            "total_milestones": self.total_milestones,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "compliance_rules": [r.to_dict() for r in self.compliance_rules],
            "cost_models": [c.to_dict() for c in self.cost_models],
            "metadata": self.metadata,
        }


def _detect_stage(text: str) -> DeployStage:
    lower = text.lower()
    for stage, keywords in _STAGE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return stage
    return DeployStage.UNKNOWN


def _extract_milestones(text: str) -> list[str]:
    ms: list[str] = []
    patterns = [
        r"(?:里程碑|milestone)[：:]\s*(.+)",
        r"(?:##\s*阶段|\*\*里程碑\d+\*\*)[：:]?\s*(.+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            ms.append(m.group(1).strip())
    bullet = r"^[-*]\s+.+?(?:目标|产出物|交付物|验证方法)[：:]\s*(.+)$"
    for m in re.finditer(bullet, text, re.MULTILINE):
        ms.append(m.group(1).strip())
    return ms


def _parse_tables(text: str, section_heading: str) -> list[TableRow]:
    rows: list[TableRow] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|") and lines[i].count("|") >= 3:
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            separator_idx = -1
            for j, tl in enumerate(table_lines):
                if re.match(r"^\|[\s\-:]+\|", tl):
                    separator_idx = j
                    break
            if separator_idx > 0:
                header_cells = [c.strip() for c in table_lines[0].split("|") if c.strip()]
                data_lines = table_lines[separator_idx + 1:]
                for dl in data_lines:
                    cells = [c.strip() for c in dl.split("|") if c.strip()]
                    if len(cells) >= 2:
                        row_dict: dict[str, str] = {}
                        for ci, cell in enumerate(cells):
                            if ci < len(header_cells):
                                row_dict[header_cells[ci]] = cell
                            else:
                                row_dict[f"col_{ci}"] = cell
                        display = " | ".join(f"{k}={v}" for k, v in row_dict.items())
                        rows.append(TableRow(cells=[display], section_heading=section_heading))
            continue
        i += 1
    return rows


def _extract_requirements(text: str) -> list[str]:
    reqs: list[str] = []
    pat = r"(?:✅|❌|必须|需要|需实现|should|must|shall|不得|不能|绝不)\s*(.+?)[。\n]"
    for m in re.finditer(pat, text):
        reqs.append(m.group(1).strip())
    for line in text.split("\n"):
        if line.strip().startswith("|") and line.count("|") >= 4:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 3:
                first = cells[0].lower()
                if any(kw in first for kw in
                       ["用途", "技术", "工具", "成本", "配置", "产能", "角色",
                        "平台", "组件", "环节", "渠道", "服务", "假设"]):
                    rest = " | ".join(cells[1:])
                    reqs.append(f"{cells[0]}: {rest}")
    return reqs


def _extract_checklists(text: str) -> list[str]:
    items: list[str] = []
    for m in re.finditer(r"-\s*\[[ x]\]\s*(.+)", text):
        items.append(m.group(1).strip())
    return items


def _extract_hypotheses(text: str) -> list[Hypothesis]:
    hypos: list[Hypothesis] = []
    for m in re.finditer(
        r"\|\s*\*\*(H\d+)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|",
        text,
    ):
        hypos.append(Hypothesis(
            name=m.group(1),
            method=m.group(2).strip(),
            pass_threshold=m.group(3).strip(),
            fail_criterion=m.group(4).strip(),
        ))
    return hypos


def _extract_compliance_rules(text: str) -> list[ComplianceRule]:
    rules: list[ComplianceRule] = []
    category_map: dict[str, str] = {
        "每日自检": "daily", "每日": "daily",
        "每周自检": "weekly", "每周": "weekly",
        "每月自检": "monthly", "每月": "monthly",
    }
    current_cat = "discipline"
    for line in text.split("\n"):
        for cn, cc in category_map.items():
            if cn in line:
                current_cat = cc
        m = re.match(r"^\d+\.\s*\*\*(.+?)\*\*", line)
        if m:
            desc = m.group(1)
            if desc not in [r.description for r in rules]:
                rules.append(ComplianceRule(
                    rule_id=f"discipline_{len(rules) + 1}",
                    description=desc,
                    category="discipline",
                ))
    for m in re.finditer(r"-\s*\[\s*[ x]\s*\]\s*(.+)", text):
        desc = m.group(1).strip()
        if desc not in [r.description for r in rules]:
            rules.append(ComplianceRule(
                rule_id=f"checklist_{len(rules) + 1}",
                description=desc,
                category=current_cat,
                is_automated=True,
            ))
    return rules


def _extract_cost_models(text: str) -> list[CostModel]:
    models: list[CostModel] = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "成本项" in line and "|" in line:
            header_cells = [c.strip() for c in line.split("|") if c.strip()]
            col_count = len(header_cells)
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].split("|") if c.strip()]
                if cells:
                    first = cells[0].strip("*").strip()
                    is_separator = all(c.replace("-", "").replace(":", "") == "" for c in cells)
                    if not is_separator and first and first != "成本项":
                        model = CostModel(stage=first)
                        for ci in range(1, min(len(cells), col_count)):
                            col_name = header_cells[ci] if ci < len(header_cells) else f"col_{ci}"
                            val_str = cells[ci].replace("¥", "").replace(",", "").replace("**", "").replace("-", "0")
                            try:
                                val = float(val_str)
                            except ValueError:
                                val = 0.0
                            model.items[col_name] = val
                        model.total = sum(model.items.values())
                        models.append(model)
                j += 1
            if models:
                break
    return models


def _parse_markdown_sections(text: str) -> list[DocumentSection]:
    lines = text.split("\n")
    stack: list[DocumentSection] = []
    root_sections: list[DocumentSection] = []
    current_section: DocumentSection | None = None
    content_lines: list[str] = []

    def _flush_content() -> None:
        if current_section is not None and content_lines:
            body = "\n".join(content_lines).strip()
            current_section.content = body
            current_section.milestones = _extract_milestones(body)
            current_section.requirements = _extract_requirements(body)
            current_section.table_rows = _parse_tables(body, current_section.heading)
            current_section.checklists = _extract_checklists(body)

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            _flush_content()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            new_section = DocumentSection(heading=heading, level=level, content="")
            if level == 1:
                root_sections.append(new_section)
                stack = [new_section]
            else:
                while stack and stack[-1].level >= level:
                    stack.pop()
                if stack:
                    stack[-1].subsections.append(new_section)
                else:
                    root_sections.append(new_section)
                stack.append(new_section)
            current_section = new_section
            content_lines = []
        else:
            content_lines.append(line)
    _flush_content()
    return root_sections


def _assign_stages_recursively(
    doc: FeatureDocument,
    sections: list[DocumentSection],
) -> None:
    for section in sections:
        stage = _detect_stage(section.heading)
        if stage == DeployStage.UNKNOWN:
            stage = _detect_stage(section.content[:500])
        if stage != DeployStage.UNKNOWN:
            if stage not in doc.stages:
                doc.stages[stage] = []
            doc.stages[stage].append(section)
        _assign_stages_recursively(doc, section.subsections)


def _extract_hypotheses_from_text(text: str) -> list[Hypothesis]:
    hypos: list[Hypothesis] = []
    for m in re.finditer(
        r"\|\s*\*\*(H[123]):\s*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|",
        text,
    ):
        hypos.append(Hypothesis(
            name=m.group(1),
            method=m.group(2).strip(),
            pass_threshold=m.group(3).strip(),
            fail_criterion=m.group(4).strip(),
        ))
    return hypos


def _extract_hypotheses_from_sections(sections: list[DocumentSection]) -> list[Hypothesis]:
    hypos: list[Hypothesis] = []
    for sec in sections:
        hypos.extend(_extract_hypotheses_from_text(sec.content))
        for sub in sec.subsections:
            hypos.extend(_extract_hypotheses_from_text(sub.content))
            for ss in sub.subsections:
                hypos.extend(_extract_hypotheses_from_text(ss.content))
                for sss in ss.subsections:
                    hypos.extend(_extract_hypotheses_from_text(sss.content))
    return hypos


class MarkdownDocIngestor:
    def ingest(self, path: str) -> FeatureDocument:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        raw = p.read_text(encoding="utf-8")

        title = p.stem
        first_line = raw.split("\n")[0].strip()
        if first_line.startswith("# "):
            title = first_line.lstrip("# ").strip()

        sections = _parse_markdown_sections(raw)

        doc = FeatureDocument(title=title, raw_path=str(p.resolve()))
        doc.all_sections = sections

        _assign_stages_recursively(doc, sections)

        doc.hypotheses = _extract_hypotheses_from_sections(sections)

        def _extract_nested(secs: list[DocumentSection]) -> None:
            for sec in secs:
                combined = sec.heading + "\n" + sec.content
                doc.compliance_rules.extend(_extract_compliance_rules(combined))
                doc.cost_models.extend(_extract_cost_models(sec.content))
                _extract_nested(sec.subsections)
        _extract_nested(sections)

        all_req_count = doc.total_requirements
        all_ms_count = doc.total_milestones

        doc.metadata = {
            "char_count": len(raw),
            "section_count": _count_all_sections(sections),
            "detected_stages": [s.value for s in doc.stages],
            "extracted_requirements": all_req_count,
            "extracted_milestones": all_ms_count,
            "hypotheses_found": len(doc.hypotheses),
            "compliance_rules_found": len(doc.compliance_rules),
            "cost_models_found": len(doc.cost_models),
        }

        return doc


def _count_all_sections(sections: list[DocumentSection]) -> int:
    count = len(sections)
    for s in sections:
        count += _count_all_sections(s.subsections)
    return count
