from maref.governance.policy_pack.builtin import (
    builtin_pack_ids,
    load_builtin_pack,
)


def test_builtin_pack_ids():
    assert "eu-ai-act@1.0.0" in builtin_pack_ids()
    assert "cn-genai@1.0.0" in builtin_pack_ids()


def test_load_builtin_by_pinned_version():
    pack = load_builtin_pack("eu-ai-act@1.0.0")
    assert pack.jurisdiction == "eu"
    assert pack.rules


def test_load_builtin_by_id_when_unique():
    pack = load_builtin_pack("eu-ai-act")
    assert pack.pack_id == "eu-ai-act"
