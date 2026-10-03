# MAREF SM2 Agent 身份证书设计（框架 3.0 附件2 二.2 对接）

- 日期：2026-10-02
- 上位法：`CONSTITUTION.md`（Athena 系统宪法 v2.4）
- 依据：《人工智能安全治理框架3.0》（TC260, 2026-09）附件2 二.2（身份与权限管理）与正文 3.2.1(a)（智能体身份标识、跨系统互认、鼓励国密）
- 实现：`src/maref/identity/sm2_certificate.py`（复用 `src/maref/crypto/aia_adapter.py`）
- 测试：`tests/identity/test_sm2_certificate.py`（18 tests，实测全绿）

## 1. 目的与范围

框架 3.0 要求智能体具备可核验的身份标识、支持跨系统身份互认，并鼓励采用国密算法。
本文描述 MAREF 在既有 ACPs AIA 国密适配层之上补齐的 **SM2 身份证书签发/验签闭环**，
以及证书身份与 `did_registry` 的绑定关系。

范围限定为**自建 CASP 签发 + 本地验签 + 导出互认**；不含外部 CA 联调（见 §7、§8）。

## 2. 证书结构（ACPs CAI）

复用 `crypto/aia_adapter.AgentIdentityCertificate`（智能体身份证书 CAI）：

| 字段 | 说明 |
|---|---|
| `agent_id` | 证书主体标识；绑定 DID 时取 `AgentDID.agent_short_id` |
| `public_key` | 主体 SM2 公钥（130 hex，未压缩 04‖X‖Y） |
| `signature` | CASP 对规范明文的 SM3withSM2 签名（hex） |
| `casp_id` | 签发机构标识 |
| `validity_period` | `(not_before, not_after)` 秒级时间戳 |

签名规范明文（`cai_plaintext`，与 `verify_cai_certificate` 严格一致）：

```
{agent_id}:{public_key}:{casp_id}:{validity_period[0]}:{validity_period[1]}
```

## 3. 签发（`issue_certificate`）

1. 由 CASP 私钥对规范明文做 `sm2_sign(..., use_sm3=True)`（SM3withSM2）；
2. 生成 `AgentIdentityCertificate`，`validity_period = (now, now + validity_days*86400)`；
3. **签发后自校验**：因 gmssl 随机数 k 极少数会产生不可验签签名，签发后立即
   `verify_cai_certificate` 自检，失败重签至多 3 次，仍失败抛 `RuntimeError`（fail-closed）。

`issue_certificate_for_did(did_string, ...)` 以 `AgentDID.parse(did_string).agent_short_id`
作为 `agent_id`，把证书主体与 MAREF DID 显式绑定。

## 4. 验证（`verify_certificate`）

返回 `VerifyResult(valid, reasons)`：

1. 签名验证：委托 `verify_cai_certificate`，失败记 `signature-invalid`；
2. 有效期窗口：`now < not_before` 记 `not-yet-valid`，`now > not_after` 记 `expired`
   （可用 `check_validity=False` 跳过，仅用于离线审计场景）。

篡改 `agent_id` / `public_key` / `casp_id` / `validity_period` 任一字段都会使签名失配而失败
（测试 `TestTampering` 逐字段覆盖）。

## 5. 与 did_registry 的绑定

- `AgentDID`（`did:maref:{namespace}:{agent_short_id}`）是 MAREF 的身份标识单一事实源；
- 证书 `agent_id` = DID 的 `agent_short_id`；
- `verify_did_binding(cert, did_string)` 校验二者一致；DID 格式非法返回 `False`。

该绑定为**标识层绑定**（同一 short_id），不做密钥绑定——DID 文档当前以 Ed25519
验证方法为主，SM2 公钥承载于证书内，两者通过 `agent_short_id` 关联。

## 6. 跨系统互认

`export_certificate(cert)` 输出含 `format: "ACPs-CAI/SM2-SM3"` 与
`public_key_fingerprint`（SM3 公钥指纹，64 hex）的字典，供对端以同一 CASP 公钥验签；
`import_certificate` 支持还原。指纹由 `sm3_fingerprint` 确定性生成。

## 7. 国家 CA / 统一身份体系对接（预留）

定义 `NationalCAAdapter` Protocol（`issue` / `verify`）作为对接接口；当前仅提供
`UnavailableNationalCAAdapter` 占位实现，任何调用抛 `NotImplementedError`（fail-closed）。

> **诚实标注**：对接国家 CA 为预留接口，未与任何外部 CA 联调；接口语义待政策细则明确后再实现。

## 8. 诚实边界（未实现 / 明确不做）

- 未采用标准 X.509 或国密证书编解码格式（现为 ACPs CAI 结构 + JSON 导出）；
- 未实现 CRL / OCSP 撤销列表与在线状态查询（撤销走 `did_registry` 生命周期）；
- 未与任何真实 CA（含国家 CA）联调；
- 未接入 SM4 加密握手套件（`crypto/sm4*` 存在但本证书链路未使用）。

以上均**未包装为已覆盖**，映射矩阵中相应条目按实际状态标注（见方案 P4 回填）。

## 9. 验证方式

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/identity/test_sm2_certificate.py -p no:cacheprovider --no-cov -q
PYTHONPATH=src .venv/bin/python -m maref.identity.sm2_certificate   # 签发→验签自检，输出 valid=true
```

## 10. 依据与事实标注

- **实测**：18 tests 全绿；`selfcheck` 输出 `valid=true`（2026-10-02）；
- **引用**：框架 3.0 附件2 二.2、正文 3.2.1(a)；ACPs AIA 协议 §3(7)（`aia_adapter` 注释）；
- **推断/预留**：国家 CA 对接语义（§7）为设计预留，非既有事实。
