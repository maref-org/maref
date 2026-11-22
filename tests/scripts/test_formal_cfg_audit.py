"""scripts/formal_cfg_audit.py 的回归测试。

背景：仓库曾有 2 个"死配置"（关键字拼写错误 / 引用了不存在的规格），
因为 CI 从不跑它们，所以永远不会变红。这个脚本把它变成可执行检查。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "formal_cfg_audit", ROOT / "scripts" / "formal_cfg_audit.py"
)
assert _spec and _spec.loader
audit_mod = importlib.util.module_from_spec(_spec)
sys.modules["formal_cfg_audit"] = audit_mod
_spec.loader.exec_module(audit_mod)


def test_repo_has_no_orphan_or_broken_cfg() -> None:
    results = audit_mod.audit(ROOT)
    assert results, "仓库里应该有 .cfg"
    bad = [r for r in results if r["status"] != "ok"]
    assert not bad, bad


def test_cfg_referencing_undefined_invariant_is_reported(tmp_path: Path) -> None:
    (tmp_path / "Mod.tla").write_text(
        "---- MODULE Mod ----\nEXTENDS Naturals\nInit == TRUE\nNext == TRUE\nSpec == Init\n====\n",
        encoding="utf-8",
    )
    (tmp_path / "ModMC.cfg").write_text(
        "SPECIFICATION Spec\nINVARIANTS\n  DoesNotExist\n", encoding="utf-8"
    )
    results = audit_mod.audit(tmp_path)
    assert results[0]["status"] == "broken"
    assert "DoesNotExist" in str(results[0]["detail"])


def test_cfg_without_any_spec_is_reported_as_orphan(tmp_path: Path) -> None:
    (tmp_path / "LonelyMC.cfg").write_text(
        "SPECIFICATION Spec\nINVARIANTS\n  Init\n", encoding="utf-8"
    )
    results = audit_mod.audit(tmp_path)
    assert results[0]["status"] == "orphan"


def test_cfg_keyword_typo_is_not_silently_ignored(tmp_path: Path) -> None:
    """`INVARIANCES` 是非法关键字：它会被当成标识符，从而暴露为 broken。"""
    (tmp_path / "Mod.tla").write_text(
        "---- MODULE Mod ----\nEXTENDS Naturals\nInit == TRUE\nSpec == Init\n====\n",
        encoding="utf-8",
    )
    (tmp_path / "ModMC.cfg").write_text(
        "SPECIFICATION Spec\nINVARIANCES\n  Init\n", encoding="utf-8"
    )
    results = audit_mod.audit(tmp_path)
    assert results[0]["status"] == "broken"
