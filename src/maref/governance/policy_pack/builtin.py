"""Built-in reference policy packs.

These are legal-reference examples, not legal advice. They are NOT enabled by
default; operators must opt in explicitly. Production deployments should
review them against the current law and their own compliance obligations.
"""

from __future__ import annotations

from maref.governance.policy_pack.schema import PolicyPack

_BUILTINS: dict[str, PolicyPack] = {
    "eu-ai-act": PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": "eu-ai-act",
            "name": "EU AI Act Reference Pack",
            "version": "1.0.0",
            "jurisdiction": "eu",
            "description": "Reference rules for EU high-risk and cross-border actions.",
            "metadata": {"status": "reference", "legal_review_required": True},
            "rules": [
                {
                    "rule_id": "eu-payment-transfer-deny",
                    "action": "payment.*",
                    "decision": "deny",
                    "priority": 100,
                    "regulation_ref": "EU AI Act Art. 6 / Annex III",
                    "description": "High-risk payment action requires prohibition or explicit approval.",
                },
                {
                    "rule_id": "eu-cross-border-defer",
                    "action": "cross_border_transfer",
                    "decision": "defer",
                    "priority": 90,
                    "regulation_ref": "GDPR Art. 44-49",
                    "description": "Cross-border transfer needs adequacy decision or SCCs.",
                    "hitl_tier": "P1",
                },
            ],
        }
    ),
    "cn-genai": PolicyPack.model_validate(
        {
            "pack_format": 1,
            "pack_id": "cn-genai",
            "name": "China Generative AI Reference Pack",
            "version": "1.0.0",
            "jurisdiction": "cn",
            "description": "Reference rules for China generative-AI and cross-border actions.",
            "metadata": {"status": "reference", "legal_review_required": True},
            "rules": [
                {
                    "rule_id": "cn-production-deploy-defer",
                    "action": "deploy.production",
                    "decision": "defer",
                    "priority": 100,
                    "regulation_ref": "CAC Generative AI Interim Measures",
                    "description": "Production deployment requires review.",
                    "hitl_tier": "P1",
                },
                {
                    "rule_id": "cn-cross-border-deny",
                    "action": "cross_border_transfer",
                    "decision": "deny",
                    "priority": 90,
                    "regulation_ref": "CSL Art. 37 / DSL Art. 36",
                    "description": "Cross-border transfer without security assessment is prohibited.",
                },
            ],
        }
    ),
}


def builtin_pack_ids() -> list[str]:
    return [f"{pack.pack_id}@{pack.version}" for pack in _BUILTINS.values()]


def load_builtin_pack(spec: str) -> PolicyPack:
    if "@" in spec:
        pack_id, version = spec.split("@", 1)
        for pack in _BUILTINS.values():
            if pack.pack_id == pack_id and pack.version == version:
                return pack
        raise KeyError(f"unknown builtin policy pack: {spec}")
    matches = [pack for pack in _BUILTINS.values() if pack.pack_id == spec]
    if len(matches) != 1:
        raise KeyError(f"expected exactly one builtin pack for {spec}, got {len(matches)}")
    return matches[0]
