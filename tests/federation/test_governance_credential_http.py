"""HTTP 端到端测试：/api/v1/federation/governance/credential/*。

使用 FastAPI TestClient 内联 create_federation_app，不起真实 uvicorn。
验证签发→查询→吊销→吊销列表的完整链路（决策 D2 HTTP 通道）。
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from maref.eivl.federated_merkle import FederatedMerkleAggregator
from maref.federation.federation_http import create_federation_app
from maref.federation.gateway import FederationGateway
from maref.federation.policy import FederationPolicyEngine
from maref.federation.policy_subscriber import FederatedPolicySubscriber
from maref.federation.trust import FederatedTrustEngine
from maref.governance.verifiable_governance_credential import GovernanceCredentialStore
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.signing.signing_key import ReportSigningKey

CRED_BASE = "/api/v1/federation/governance/credential"


def _hash(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


@pytest.fixture
def client() -> TestClient:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(), local_org="org-1"
    )
    store = GovernanceCredentialStore()
    app = create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id="org-1",
        governance_credentials=store,
        credential_signing_key=ReportSigningKey.generate(),
        merkle_aggregator=FederatedMerkleAggregator(),
    )
    return TestClient(app)


def _issue_body(subject: str = "did:maref:agent-alice", **overrides: object) -> dict:
    body: dict[str, object] = {
        "subject_did": subject,
        "issuer_did": "did:maref:org-governor",
        "scope": ["state_machine", "audit"],
    }
    body.update(overrides)
    return body


class TestIssue:
    def test_issue_returns_credential(self, client: TestClient) -> None:
        resp = client.post(f"{CRED_BASE}/issue", json=_issue_body())
        assert resp.status_code == 200
        data = resp.json()
        assert data["credential"]["subject_did"] == "did:maref:agent-alice"
        assert data["verification"]["valid"] is True

    def test_issue_with_org_root_binds_merkle(self, client: TestClient) -> None:
        resp = client.post(
            f"{CRED_BASE}/issue",
            json=_issue_body(
                org_id="org-1", root_hash=_hash("org-1-root"), tree_size=10
            ),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verification"]["merkle_valid"] is True

    def test_issue_missing_subject_400(self, client: TestClient) -> None:
        body = _issue_body()
        del body["subject_did"]
        resp = client.post(f"{CRED_BASE}/issue", json=body)
        assert resp.status_code == 400

    def test_issue_invalid_scope_400(self, client: TestClient) -> None:
        resp = client.post(f"{CRED_BASE}/issue", json=_issue_body(scope=["nope"]))
        assert resp.status_code == 400

    def test_issue_empty_scope_400(self, client: TestClient) -> None:
        resp = client.post(f"{CRED_BASE}/issue", json=_issue_body(scope=[]))
        assert resp.status_code == 400

    def test_issue_scope_string_400(self, client: TestClient) -> None:
        resp = client.post(f"{CRED_BASE}/issue", json=_issue_body(scope="audit"))
        assert resp.status_code == 400


class TestQueryAndRevoke:
    def test_get_credential(self, client: TestClient) -> None:
        issued = client.post(f"{CRED_BASE}/issue", json=_issue_body()).json()
        cid = issued["credential"]["credential_id"]
        resp = client.get(f"{CRED_BASE}/{cid}")
        assert resp.status_code == 200
        assert resp.json()["verification"]["valid"] is True

    def test_get_unknown_404(self, client: TestClient) -> None:
        resp = client.get(f"{CRED_BASE}/vgc-does-not-exist")
        assert resp.status_code == 404

    def test_revoke_marks_credential(self, client: TestClient) -> None:
        issued = client.post(f"{CRED_BASE}/issue", json=_issue_body()).json()
        cid = issued["credential"]["credential_id"]
        rev = client.post(
            f"{CRED_BASE}/{cid}/revoke",
            json={"reason": "state drift", "source": "did-revocation:did:maref/x"},
        )
        assert rev.status_code == 200
        got = client.get(f"{CRED_BASE}/{cid}").json()
        assert got["verification"]["revoked"] is True
        assert got["verification"]["valid"] is False

    def test_revocation_list_export(self, client: TestClient) -> None:
        issued = client.post(f"{CRED_BASE}/issue", json=_issue_body()).json()
        cid = issued["credential"]["credential_id"]
        client.post(f"{CRED_BASE}/{cid}/revoke", json={"reason": "override"})
        lst = client.get(f"{CRED_BASE}/revocation-list").json()
        assert lst["revoked"][cid] == "override"

    def test_revocation_list_signed(self, client: TestClient) -> None:
        issued = client.post(f"{CRED_BASE}/issue", json=_issue_body()).json()
        cid = issued["credential"]["credential_id"]
        client.post(f"{CRED_BASE}/{cid}/revoke", json={"reason": "override"})
        lst = client.get(f"{CRED_BASE}/revocation-list").json()
        assert lst["signature"]
        assert lst["signer_public_key_pem"]
        assert GovernanceCredentialStore.verify_signed_revocation_list(lst) is True

    def test_revocation_list_tamper_detected(self, client: TestClient) -> None:
        issued = client.post(f"{CRED_BASE}/issue", json=_issue_body()).json()
        cid = issued["credential"]["credential_id"]
        client.post(f"{CRED_BASE}/{cid}/revoke", json={"reason": "override"})
        lst = client.get(f"{CRED_BASE}/revocation-list").json()
        lst["revoked"] = {}
        assert GovernanceCredentialStore.verify_signed_revocation_list(lst) is False


def test_unconfigured_store_503() -> None:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(), local_org="org-1"
    )
    app = create_federation_app(gateway, trust_engine, subscriber, server_id="org-1")
    resp = TestClient(app).get(f"{CRED_BASE}/revocation-list")
    assert resp.status_code == 503
