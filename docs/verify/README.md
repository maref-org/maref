# MAREF Governance Report — 公开审计报告

本目录包含 MAREF 的治理审计报告，通过 Ed25519 签名确保其不可篡改。

## 文件结构

- `latest.json` — 最新治理报告（JSON）
- `latest.html` — 最新治理报告（HTML 自包含页面）
- `report-<时间戳>.json` — 每次部署的归档报告
- `<report_id 前 8 位>.html` — 单份报告的 HTML 页面，索引中的链接指向这里
- `index.html` — 历史报告索引页
- `fingerprint.txt` — 当前签名公钥指纹
- `maref-report-signing.pub` — 当前签名公钥（固定名别名）
- `keys/<fingerprint>.pub` — 按指纹归档的公钥；密钥轮换后旧公钥仍保留，历史报告仍可验证

## 验证方式

```bash
FP=$(cat fingerprint.txt)
curl -o latest.json https://maref.cc/verify/latest.json
curl -o key.pub "https://maref.cc/verify/keys/${FP}.pub"

maref report verify --file latest.json --pubkey key.pub
```

四项检查全部通过即为 `VERIFIED`：签名存在、签名有效、指纹匹配、Merkle 根一致。
`latest.json` 中的 `signer_fingerprint` 必须同时等于 `fingerprint.txt` 与站外公布的指纹。

## 签名密钥

报告使用独立的 `maref-report-signing` Ed25519 密钥签署，仅用于报告签署，**不**与审计链共享。
私钥只保存在 CI secret（`MAREF_REPORT_SIGNING_KEY`）中，公钥与指纹随每次部署公开。

轮换密钥时无需手工归档旧公钥：部署流程会按指纹写入 `keys/<fingerprint>.pub` 并保留历史，
因此每份历史报告都能用其签署时的公钥独立验证。
