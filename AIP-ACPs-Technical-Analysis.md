# AIP (ACPs) Protocol Technical Analysis & MAREF Gap Assessment

> Generated: 2026-05-27  
> Source: AIP-PUB GitHub Organization + aip.openatom.tech

---

## 1. Organization Overview

**AIP-PUB** (6 public repos, 62 stars, led by Beijing Univ. of Posts & Telecom + CESI):

| Repository | Language | Description |
|---|---|---|
| `Agent-Interconnection-Protocol-Project` | Spec docs | ACPs v2.00 protocol family specification (8 specs) |
| `ACPs-SDK` | Python | SDK for AIP protocol implementation |
| `ACPs-Demo-Project` | Python | Reference demo (Beijing tourism multi-agent) |
| `ACPs-Registry-Server` | Python | Agent registration server (FastAPI) |
| `ACPs-Discovery-Server` | Python | Agent discovery server (FastAPI + Embedding) |
| `ACPs-CA-Server` | Python | Certificate authority server |
| `ACPs-CA-Client` | Python | CA client tool |
| `ACPs-CA-Challenge` | Shell | Challenge verification for cert issuance |

**Standardization**: Being submitted as Chinese national standard GB/Z (guiding technical document) under the "AI Agent Interconnection" series, managed by CESI (China Electronics Standardization Institute).

---

## 2. ACPs Protocol Family — 8 Specs

### 2.1 AIC — Agent Identity Code (身份码规范)
- **Hierarchical OID-based identifier** using dot-separated notation
- Format: `1.2.156.3088.<ARSP#.<ProviderID>.<OntologySeq>.<EntitySeq>.<Version>.<Checksum>`
  - `1.2.156.3088` = ISO → country member → China → AIP-specific OID node
- Checksum: AUTOSAR CRC-16/CCITT-FALSE + per-ARSP salt + Base36 encoding
- Concepts: **Ontology** (class-level, entity-seq=0) vs **Entity** (instance-level, entity-seq≠0)
- Up to ~10^14 entities per ontology (36^9 combos)
- **Status**: v2.00, stable

### 2.2 ACS — Agent Capability Specification (能力描述规范)
- JSON Schema based capability description:
  - `AgentCapabilitySpec`: aic, active, lastModifiedTime, protocolVersion, name, description, version
  - `AgentProvider`: organization, department, url, license, contact
  - `AgentCapabilities`: streaming(bool), notification(bool), messageQueue(MQProtocol[])
  - `SecurityScheme`: mutualTLS, openIdConnect, apiKey, http, oauth2
  - `AgentEndPoint`: url, transport(JSONRPC|HTTP_JSON), security[]
  - `AgentSkill`: id, name, description, version, tags, examples, inputModes, outputModes
- Well-known URL: `https://agent.example.com/.well-known/acs.json`
- **Status**: v2.00, stable

### 2.3 ATR — Agent Trusted Registration (可信注册规范)
- Two-phase registration:
  - **Ontology Registration**: ARSP assigns AIC after manual review → CA Server issues certificate via ACME-like challenge
  - **Entity Registration**: Uses mTLS with ontology cert → ARSP auto-generates entity AIC → Gets entity cert
- Challenge mechanism: token-based HTTP-01 validation (similar to ACME)
- **Status**: v2.00, stable

### 2.4 AIA — Agent Identity Authentication (身份认证规范)
- **Primary**: TLS 1.3 mTLS (mutual TLS) for agent-to-agent authentication
- **User auth**: OIDC (OpenID Connect) for human-to-agent
- Certificate verification: hash chain validation using CASP's public key
- **Status**: v2.00, stable

### 2.5 ADP — Agent Discovery Protocol (发现协议)
- **Rich**: Full TypeScript-like API spec with:
  - `POST /discover` with mTLS auth
  - Query types: explicit, exploratory, trending, filtered
  - Structured filter system (MongoDB-like): conditions + groups + logic (AND/OR/NOT)
  - 40+ filter operators (eq, ne, gt, gte, lt, lte, between, in, nin, contains, startsWith, endsWith, anyOf, allOf, hasKey, size, exists + case-sensitive variants)
  - Multi-server collaboration: Redirect (307), Chain Forwarding, Fan-out Aggregation
  - Forward chain integrity: signed `forwardChain` + `forwardSignatures`
- Response: `DiscoveryResult` with `acsMap`, `agents`, `routes`
- **Status**: v2.00, highly detailed

### 2.6 AIP — Agent Interaction Protocol (交互协议)
- Two roles: **Leader** (task issuer) and **Partner** (task executor)
- Three interaction modes:
  1. **Direct (RPC/SSE/Async Notification)**: Leader ↔ Partner 1:1
  2. **Group (Message Queue)**: Via RabbitMQ, all members see messages
  3. **Hybrid**: Mix of direct + group in same Session
- Core data objects:
  - `Message`: type, id, sentAt, senderRole, senderId, mentions, dataItems, groupId, sessionId
  - `TaskCommand`: Start, Continue, Cancel, Complete, Get, ReStream
  - `TaskResult`: TaskStatus with state machine
  - `DataItem`: TextDataItem, FileDataItem, StructuredDataItem
  - `Product`: named result artifact
- **Task State Machine**: Accepted → Working → AwaitingInput/AwaitingCompletion → Completed/Failed/Canceled
- **Status**: v2.00, stable (SDK references v02.00)

### 2.7 DSP — Data Synchronization Protocol (数据同步协议)
- Provider-Consumer model for syncing ACS data from Registry Server to Discovery Server
- Three sync mechanisms:
  1. **Snapshot** (full/incremental, chunked for large data)
  2. **Changes** (sequential delta, long-polling, retention window)
  3. **Webhook Notification** (push-based, batch/immediate, callback verification)
- Envelope data model: `{seq, ts, op, type, id, version, payload}` with `(type, id, version)` idempotency
- **Status**: v2.00, stable

---

## 3. SDK Architecture (`acps_sdk`)

```
acps_sdk/
├── acs/           # ACS parsing/validation
├── adp/           # ADP discovery client
├── aic/           # AIC generation/validation (CRC-16/BASE36)
└── aip/           # Core interaction protocol (most mature)
    ├── aip_base_model.py     # Message, TaskCommand, TaskResult, DataItem, etc.
    ├── aip_rpc_model.py      # JSON-RPC 2.0 request/response
    ├── aip_rpc_client.py     # Leader RPC client
    ├── aip_rpc_server.py     # Partner RPC server (CommandHandlers, FastAPI integration)
    ├── aip_stream_model.py   # SSE streaming model
    ├── aip_group_model.py    # Group/RabbitMQ message model
    ├── aip_group_leader.py   # GroupLeaderMqClient, GroupLeaderSession
    ├── aip_group_partner.py  # GroupPartnerMqClient
    └── mtls_config.py        # mTLS configuration
```

**Tech stack**: Python 3.13+, FastAPI, Pydantic, RabbitMQ, Poetry  
**Communication**: JSON-RPC 2.0 over HTTPS with mTLS

---

## 4. Demo Architecture (ACPs-Demo-Project)

```
leader/         → FastAPI app (LLM orchestration, task decomposition)
partners/       → FastAPI apps (generic runtime + config-driven agents)
  online/
    beijing_urban/   → ACS + config + prompts
    beijing_rural/
    beijing_food/
    china_transport/
    china_hotel/
web_app/        → Vanilla JS frontend (polling)
```

- Leader uses LLM (OpenAI-compatible API) for intent analysis, task decomposition, partner selection
- Partners use "generic runtime + config-driven" architecture (add agent = add config files)
- Supports both Direct RPC and Group (RabbitMQ) modes

---

## 5. MAREF Existing Capabilities Map

| Capability | MAREF Status | ACPs Equivalent | Gap |
|---|---|---|---|
| **SM2/SM3/SM4 Crypto** | ✅ `src/maref/crypto/sm2.py, sm3.py, sm4.py, sm4_gcm.py` | AIC CRC-16 uses non-GM algorithms | **No gap** for crypto — but ACPs uses standard TLS/AUTOSAR CRC, not SM-crypto |
| **DID/VC Identity** | ✅ `src/maref/identity/did_registry.py`, `trust_engine.py`, `security/agent_identity/` | AIC (OID-based) + CAI (X.509 cert) | **Structural gap**: MAREF uses `did:maref:*`; ACPs uses hierarchical OID AIC `1.2.156.3088.*` |
| **A2A/MCP Bridge** | ✅ `src/maref/integration/a2a_bridge.py`, `src/maref/protocols/protocol_bridge.py` | AIP (Leader-Partner RPC) | **Protocol gap**: A2A is Google's agent protocol; ACPs AIP uses JSON-RPC 2.0 + mTLS with custom task state machine |
| **TaskGraph Orchestration** | ✅ `src/maref/orchestration/task_graph.py`, `plan_executor.py`, `dispatcher.py` | AIP Session + TaskCommand + Product | **Architecture gap**: MAREF's TaskGraph is DAG-based; ACPs AIP is Leader-Partner with linear task state machine |
| **Agent Discovery** | ⚠️ Basic `dispatcher.py` capability lookup | ADP (rich structured queries, multi-server forwarding, filter system) | **Major gap**: MAREF lacks structured agent discovery with full filter/query semantics |
| **Agent Registration** | ⚠️ `role_registry.py` + `did_registry.py` | ATR (full life-cycle: ontology → entity, ACME-like challenge, cert issuance) | **Major gap**: No formal registration + certificate issuance pipeline |
| **Data Sync (Registry→Discovery)** | ❌ Not present | DSP (snapshot/changes/webhook) | **Missing**: No data synchronization protocol |
| **Capability Description** | ⚠️ `dispatcher.py` uses `list[str]` for capabilities | ACS (full schema: skills, endpoints, security schemes, MQ, streaming) | **Major gap**: MAREF has no structured capability schema |
| **mTLS Infrastructure** | ⚠️ Security proofs, trust engine | mTLS + CA server + OCSP + CRL | **Major gap**: No full PKI infrastructure |
| **Message Queue Group Mode** | ❌ Not present | RabbitMQ-based group interaction | **Missing**: No MQ-based multi-agent collaboration |
| **Task State Machine** | ❌ No formal task lifecycle | AIP 8-state machine (Accepted→Working→AwaitingInput→AwaitingCompletion→Completed) | **Missing**: No standardized task lifecycle |
| **Standardization Path** | ❌ MAREF is proprietary | Being submitted as Chinese GB/Z national standard | **Strategy gap**: ACPs has gov't/standards body backing |

---

## 6. Key Technical Differences

### 6.1 Identity Model
| Aspect | MAREF (DID) | ACPs (AIC) |
|---|---|---|
| Format | `did:maref:{namespace}:{short_id}` | `1.2.156.3088.{ARSP}.{Provider}.{Onto}.{Entity}.{Ver}.{CRC}` |
| Underlying | W3C DID standard | OID (Object Identifier) standard |
| Checksum | None | AUTOSAR CRC-16/CCITT-FALSE + salt |
| Verification | DID Resolution | Certificate-based (mTLS) |
| Lifecycle | Simple register/resolve | Ontology→Entity two-phase with cert challenge |

### 6.2 Interaction Model
| Aspect | MAREF (MCP/A2A Bridge) | ACPs (AIP) |
|---|---|---|
| Protocol | Protobuf-like (MCP) + JSON (A2A) | JSON-RPC 2.0 over HTTPS |
| Transport | HTTP/SSE | HTTPS + mTLS |
| Mode | Tool call ↔ Task | Direct RPC / Group MQ / Hybrid |
| State machine | Simple success/failure | 8-state: Accepted→Working→AwaitingInput→AwaitingCompletion→Completed |
| Group mode | Not supported | RabbitMQ-based (mentions, broadcast) |

### 6.3 Discovery Model
| Aspect | MAREF | ACPs (ADP) |
|---|---|---|
| Interface | Simple capability string matching | MongoDB-like structured filter with 40+ operators |
| Multi-server | Not supported | Redirect/Chain/Fan-out with cryptographic integrity |
| Query types | None | explicit, exploratory, trending, filtered |
| Caching | None | HTTP Cache-Control + ETag |

---

## 7. Recommended Integration Strategy for MAREF

**Phase 1 — Bridge (Low effort, high value)**:
1. Implement AIC generation/validation module (CRC-16 + Base36 + salt)
2. Build ACS schema parser/validator for MAREF agents
3. Create AIP message adapter: map MAREF's internal TaskGraph nodes ↔ AIP TaskCommand/TaskResult

**Phase 2 — Protocol Adapter (Medium effort)**:
4. Implement ADP client: query ACPs discovery servers for partner agents
5. Build AIP RPC server: expose MAREF agents as ACPs-compatible Partners
6. Add mTLS cert management: integrate with MAREF's existing SM2 crypto for cert signing

**Phase 3 — Full Interop (High effort)**:
7. Implement DSP consumer: sync agent data from Registry Servers
8. Implement ATR client: register MAREF agents with ACPs registries
9. Add Group mode: RabbitMQ bridge for MAREF's TaskGraph orchestration

### Priority Gaps to Fill
1. **Structured ACS capability description** (MAREF uses flat string lists)
2. **ADP discovery client** with structured filter queries
3. **AIP task state machine** integration with existing TaskGraph
4. **mTLS-based identity** for agent-to-agent auth (bridge to existing SM2 keys)
5. **Data sync protocol** (DSP) for distributed agent registries

---

## 8. Key Links

- ACPs Project: https://github.com/AIP-PUB/Agent-Interconnection-Protocol-Project
- ACPs SDK: https://github.com/AIP-PUB/ACPs-SDK
- Demo Project: https://github.com/AIP-PUB/ACPs-Demo-Project
- Registry Server: https://github.com/AIP-PUB/ACPs-Registry-Server
- Discovery Server: https://github.com/AIP-PUB/ACPs-Discovery-Server
- CA Server: https://github.com/AIP-PUB/ACPs-CA-Server
- CA Client: https://github.com/AIP-PUB/ACPs-CA-Client
- Community: https://aip.openatom.tech/
- Standard (WeChat): https://mp.weixin.qq.com/s/ZE8VWy8LJoawTMd_gwu1qw
