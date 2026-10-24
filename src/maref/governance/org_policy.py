"""Organization-scoped policy and role-based access control.

This module supplies the multi-organization policy layer requested by the
enterprise governance roadmap.  A policy file maps organization ids to role
definitions; each role may allow, deny, or require human approval for action
patterns.  Patterns use ``fnmatch`` syntax (``file.*``, ``shell.exec``, ``*``).

Unknown organizations are "unmanaged" by default so existing single-tenant
deployments are not broken.  Set ``strict: true`` at the document root to make
unknown organizations fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal

import yaml

OrgDecision = Literal["allow", "deny", "require_approval", "unmanaged"]


@dataclass(frozen=True)
class RolePolicy:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    require_approval: tuple[str, ...] = ()
    inherits: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrgPolicyDecision:
    decision: OrgDecision
    reason: str
    policy_version: str = ""
    policy_epoch: str = ""
    matched_rule: str = ""


@dataclass
class OrganizationPolicy:
    organizations: dict[str, dict[str, RolePolicy]] = field(default_factory=dict)
    default_decision: OrgDecision = "deny"
    unknown_role_decision: OrgDecision = "deny"
    strict: bool = False
    policy_version: str = ""
    policy_epoch: str = ""
    source: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> OrganizationPolicy:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Organization policy not found: {source}")
        data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        return cls.from_dict(data, source=str(source))

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "") -> OrganizationPolicy:
        organizations: dict[str, dict[str, RolePolicy]] = {}
        for org_id, org_data in (data.get("organizations") or {}).items():
            roles: dict[str, RolePolicy] = {}
            for role_id, role_data in (org_data.get("roles") or {}).items():
                role_data = role_data or {}
                roles[str(role_id)] = RolePolicy(
                    allow=tuple(str(value) for value in role_data.get("allow", [])),
                    deny=tuple(str(value) for value in role_data.get("deny", [])),
                    require_approval=tuple(
                        str(value) for value in role_data.get("require_approval", [])
                    ),
                    inherits=tuple(str(value) for value in role_data.get("inherits", [])),
                )
            organizations[str(org_id)] = roles

        return cls(
            organizations=organizations,
            default_decision=_decision(data.get("default_decision", "deny")),
            unknown_role_decision=_decision(data.get("unknown_role_decision", "deny")),
            strict=bool(data.get("strict", False)),
            policy_version=str(data.get("version", "")),
            policy_epoch=str(data.get("epoch", "")),
            source=source,
        )

    def evaluate(self, org_id: str, role: str, action: str) -> OrgPolicyDecision:
        if not org_id or org_id not in self.organizations:
            decision: OrgDecision = "deny" if self.strict else "unmanaged"
            reason = (
                f"Organization '{org_id}' is not managed (strict fail-closed)"
                if self.strict
                else f"Organization '{org_id}' is not managed"
            )
            return self._decision(decision, reason)

        roles = self.organizations[org_id]
        effective = self._effective_roles(roles, role)
        if effective is None:
            return self._decision(
                self.unknown_role_decision,
                f"Unknown role '{role}' in organization '{org_id}'",
            )

        for role_policy in effective:
            match = _match(role_policy.deny, action)
            if match:
                return self._decision(
                    "deny",
                    f"Role '{role}' denies '{action}' (pattern {match})",
                    "org_policy:deny",
                )

        for role_policy in effective:
            match = _match(role_policy.require_approval, action)
            if match:
                return self._decision(
                    "require_approval",
                    f"Role '{role}' requires approval for '{action}' (pattern {match})",
                    "org_policy:require_approval",
                )

        for role_policy in effective:
            if _match(role_policy.allow, action):
                return self._decision(
                    "allow",
                    f"Role '{role}' allows '{action}'",
                    "org_policy:allow",
                )

        return self._decision(
            self.default_decision,
            f"No organization rule matched role '{role}' action '{action}'",
            "org_policy:default",
        )

    def _effective_roles(
        self,
        roles: dict[str, RolePolicy],
        role: str,
    ) -> list[RolePolicy] | None:
        if role not in roles:
            return None
        resolved: list[RolePolicy] = []
        visiting: set[str] = set()

        def visit(name: str) -> None:
            policy = roles.get(name)
            if policy is None or name in visiting:
                return
            visiting.add(name)
            for parent in policy.inherits:
                visit(parent)
            resolved.append(policy)

        visit(role)
        return resolved

    def _decision(
        self,
        decision: OrgDecision,
        reason: str,
        matched_rule: str = "",
    ) -> OrgPolicyDecision:
        return OrgPolicyDecision(
            decision=decision,
            reason=reason,
            policy_version=self.policy_version,
            policy_epoch=self.policy_epoch,
            matched_rule=matched_rule,
        )


def _match(patterns: tuple[str, ...], action: str) -> str:
    for pattern in patterns:
        if fnmatchcase(action, pattern):
            return pattern
    return ""


def _decision(value: Any) -> OrgDecision:
    text = str(value or "").lower()
    if text in ("allow", "deny", "require_approval", "unmanaged"):
        return text  # type: ignore[return-value]
    return "deny"
