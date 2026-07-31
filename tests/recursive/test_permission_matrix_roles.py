"""
Roles: 坎, 震, 离, 坤, 艮.
"""

from __future__ import annotations

from maref.recursive.permission_matrix import PermissionMatrix


class TestPermissionMatrixAllRoles:
    def test_all_five_roles_present(self):
        matrix = PermissionMatrix()
        roles = {e.role for e in matrix._entries}
        assert roles == {"坎", "震", "离", "坤", "艮"}

    # ── 坎 (observer) ──
    def test_kan_allowed_tools(self):
        assert PermissionMatrix().check("坎", "search")
        assert PermissionMatrix().check("坎", "query")
        assert PermissionMatrix().check("坎", "read")

    def test_kan_denied_tools(self):
        assert not PermissionMatrix().check("坎", "write")
        assert not PermissionMatrix().check("坎", "delete")
        assert not PermissionMatrix().check("坎", "execute")

    def test_kan_no_approval_required(self):
        entry = PermissionMatrix().get_permissions("坎")
        assert entry is not None
        assert not entry.require_approval

    # ── 震 (executor) ──
    def test_zhen_allowed_tools(self):
        assert PermissionMatrix().check("震", "write")
        assert PermissionMatrix().check("震", "build")

    def test_zhen_denied_tools(self):
        assert not PermissionMatrix().check("震", "sudo")
        assert not PermissionMatrix().check("震", "bash")

    def test_zhen_requires_approval(self):
        entry = PermissionMatrix().get_permissions("震")
        assert entry is not None
        assert entry.require_approval

    def test_zhen_forbidden_operations(self):
        assert not PermissionMatrix().check_operation("震", "rm -rf /data")
        assert not PermissionMatrix().check_operation("震", "DROP TABLE users")

    # ── 离 (critic) ──
    def test_li_allowed_tools(self):
        assert PermissionMatrix().check("离", "review")
        assert PermissionMatrix().check("离", "lint")
        assert PermissionMatrix().check("离", "analyze")

    def test_li_denied_tools(self):
        assert not PermissionMatrix().check("离", "write")
        assert not PermissionMatrix().check("离", "execute")

    def test_li_low_entropy(self):
        entry = PermissionMatrix().get_permissions("离")
        assert entry is not None
        assert entry.max_entropy == 4.0

    # ── 坤 (memory) ──
    def test_kun_allowed_tools(self):
        assert PermissionMatrix().check("坤", "store")
        assert PermissionMatrix().check("坤", "retrieve")
        assert PermissionMatrix().check("坤", "load")

    def test_kun_denied_tools(self):
        assert not PermissionMatrix().check("坤", "delete")
        assert not PermissionMatrix().check("坤", "bash")

    def test_kun_lowest_entropy(self):
        entry = PermissionMatrix().get_permissions("坤")
        assert entry is not None
        assert entry.max_entropy == 3.0

    def test_kun_entropy_exceeded(self):
        assert not PermissionMatrix().check("坤", "store", entropy=5.0)

    # ── 艮 (auditor) ──
    def test_gen_allowed_tools(self):
        assert PermissionMatrix().check("艮", "audit")
        assert PermissionMatrix().check("艮", "verify")
        assert PermissionMatrix().check("艮", "inspect")

    def test_gen_denied_tools(self):
        assert not PermissionMatrix().check("艮", "write")
        assert not PermissionMatrix().check("艮", "delete")
        assert not PermissionMatrix().check("艮", "execute")

    def test_gen_lowest_entropy(self):
        entry = PermissionMatrix().get_permissions("艮")
        assert entry is not None
        assert entry.max_entropy == 2.0

    def test_gen_entropy_exceeded(self):
        assert not PermissionMatrix().check("艮", "audit", entropy=3.0)

    def test_gen_forbidden_bypass_operations(self):
        assert not PermissionMatrix().check_operation("艮", "bypass_safety_gate")
        assert not PermissionMatrix().check_operation("艮", "disable_hooks")

    # ── Cross-role edge cases ──
    def test_unknown_role_denied(self):
        assert not PermissionMatrix().check("unknown", "search")

    def test_unknown_role_operation_denied(self):
        assert not PermissionMatrix().check_operation("unknown", "any")

    def test_get_all_permissions_returns_all_roles(self):
        perms = PermissionMatrix().get_all_permissions()
        role_names = [p["role"] for p in perms]
        assert set(role_names) == {"坎", "震", "离", "坤", "艮"}
