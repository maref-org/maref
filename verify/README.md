# MAREF Governance Report — 公开审计报告

本目录包含 MAREF 的治理审计报告，通过 Ed25519 签名确保其不可篡改。

## 文件结构

- `latest.json` — 最新治理报告（JSON）
- `latest.html` — 最新治理报告（HTML 自包含页面）
- `index.html` — 历史报告索引页
- `fingerprint.txt` — 当前签名公钥指纹（用于离线验证）

## 验证方式

```bash
# 下载报告和指纹
curl -O https://maref.cc/verify/latest.json
curl -O https://maref.cc/verify/fingerprint.txt

# 离线验证
maref report verify --file latest.json --pubkey <(echo "public key from fingerprint")
```

或直接通过 CLI 在线验证：

```bash
curl https://maref.cc/verify/latest.json | maref report verify --file -
```

## 签名密钥

报告使用独立的 `maref-report-signing` Ed25519 密钥签署。
此密钥仅用于报告签署，**不**与审计链（v0.38.0）共享。
指纹公布在 `fingerprint.txt` 中。
