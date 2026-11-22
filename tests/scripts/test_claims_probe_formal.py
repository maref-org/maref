"""形式化 / OWASP 声称的回归（复盘 A3，2026-11-22）。

背景：README 长期同时写"4 TLA+ specs"与"13 with TLA+ specs"，而 mapping 文档写
TLA+ 覆盖 4/10。这三个数字互不相干，也没有任何门禁拦住——因为 claims.yaml 只登记
版本/测试/覆盖率，规则写"任何数字"却只覆盖 13 条。

本文件锁三件事：
1. 新登记的探针与仓库实况一致（不是硬编码字符串）；
2. README 不再出现"整体 formally-verified"这类无法界定的定语；
3. claims.yaml 里确实有这 6 条，防止有人删掉登记却留着 README 数字。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = ROOT / "scripts" / "claims_probe.py"
README = ROOT / "README.md"
MAPPING_DOC = ROOT / "docs" / "security" / "owasp-agentic-top10-mapping.md"
WORKFLOW = ROOT / ".github" / "workflows" / "formal-verify.yml"


def _load_probe():
    spec = importlib.util.spec_from_file_location("maref_claims_probe_formal", PROBE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()


def test_tlc_jobs_match_workflow_invocations() -> None:
    invocations = len(re.findall(r"tlc2\.TLC", WORKFLOW.read_text(encoding="utf-8")))

    assert invocations == 4, f"formal-verify.yml 里 TLC 调用应为 4 处，实测 {invocations}"
    assert probe.formal_tlc_jobs() == str(invocations)


def test_spec_counts_match_filesystem() -> None:
    tla = [p for p in ROOT.rglob("*.tla") if not probe._SKIP_DIRS & set(p.parts)]
    cfg = [p for p in ROOT.rglob("*.cfg") if not probe._SKIP_DIRS & set(p.parts)]

    assert probe.formal_specs() == str(len(tla))
    assert probe.formal_cfg() == str(len(cfg))
    # 只记录"存在多少"，不假装"检查多少"。
    assert int(probe.formal_specs()) > int(probe.formal_tlc_jobs())


def test_owasp_risks_and_tla_anchor_agree() -> None:
    doc = MAPPING_DOC.read_text(encoding="utf-8")

    assert probe.owasp_risks() == "10"
    assert probe.owasp_tla_specs() == "4"
    assert f"{probe.owasp_tla_specs()}/10" in doc, "mapping 文档的 TLA+ 覆盖率行与探针不一致"


def test_conformance_controls_is_ten() -> None:
    assert probe.conformance_controls() == "10"


def test_readme_formal_wording_is_scoped() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "formally-verified agent governance operating system" not in readme, (
        "README 又出现了无法界定的整体 formally-verified 定语；应写明被检查的是哪几个规格"
    )
    assert "4 TLC jobs" in readme
    assert "13 with TLA+ specs" not in readme


def test_claims_ledger_registers_formal_family() -> None:
    data = yaml.safe_load((ROOT / "claims.yaml").read_text(encoding="utf-8"))
    ids = {claim["id"] for claim in data["claims"]}

    for needed in (
        "formal.tlc_jobs",
        "formal.specs",
        "formal.cfg",
        "conformance.controls",
        "owasp.risks_documented",
        "owasp.tla_specs",
    ):
        assert needed in ids, f"claims.yaml 缺少 {needed}"


def test_claims_rule_is_narrowed_to_measurable_properties() -> None:
    """规则文本必须与实现同宽；否则又会退化成"写了但没人执行"。"""
    text = (ROOT / "claims.yaml").read_text(encoding="utf-8")

    assert "本仓可度量的属性" in text
    assert "引用第三方调研的数字" in text
