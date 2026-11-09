# MAREF Governance Report — 公开治理报告

本目录发布 MAREF 的每日治理报告。报告由 Ed25519 签名，并绑定当日审计链锚点
（RFC 3161 时间戳）与每日门禁摘要，任何第三方都可在下载后离线复验。

## 文件结构

- `latest.json` — 最新报告；`report-<UTC时间戳>.json` 为归档副本
- `latest.html` / `index.html` — 人读版本与历史索引
- `maref-report-signing.pub` — 报告签名公钥（指纹见报告 `signer_fingerprint`）
- `anchors/<YYYYMMDD>/` — 当日锚点：`ANCHOR_MANIFEST.json`、`anchors.jsonl`、
  `batches/*.tsr|.tsq`（FreeTSA 令牌）、`freetsa-cacert.pem`
- `gates/<YYYYMMDD>.json` — 当日全部门禁状态与退出码

只发布聚合计数与哈希：不包含审计原文、actor 名称、事件详情或本机路径。

## 报告字段含义

- `metadata.scope.status` — `healthy | degraded | no_data`
  - `healthy` 仅表示：证据链完整、锚点齐全、当日全部门禁通过
  - 不表示单个 agent 的行为质量，也不评价治理决策本身
- `metadata.anchor` — 锚点清单哈希、审计文件哈希、批次 Merkle 根与 TSA 信息
- `metadata.gates` — 每个门禁的名称、状态、退出码与门禁摘要文件哈希
- `previous_report_id` — 上一份报告的 `report_id`，用于校验报告链连续

## 验证方式

```bash
git clone --depth=1 https://github.com/maref-org/maref
cd maref
python3 -m pip install -e ".[identity]"
git fetch --depth=1 origin gh-pages:refs/remotes/origin/gh-pages
git archive origin/gh-pages verify | tar -x

python3 scripts/verify_public_report.py \
  --report verify/latest.json \
  --pubkey verify/maref-report-signing.pub \
  --anchor-root verify/anchors \
  --gates-dir verify/gates
```

逐项校验：

1. 报告签名（payload 为除 `signature` 外的全部字段）
2. `metadata.anchor.manifest_sha256` 等于下载到的 `ANCHOR_MANIFEST.json` 字节哈希
3. `metadata.anchor` 各字段与清单一致
4. 每项门禁的 `evidence_sha256` 等于当日门禁摘要文件哈希，且状态/退出码一致
5. `scope.status` 与门禁、事件数自洽（无数据必须为 `no_data`）
6. 如提供 `--previous-report`，则校验报告链连续

锚点本身可用同仓脚本复核（令牌签名与 manifest/anchors 一致性）：

```bash
python3 scripts/verify_anchor_manifest.py --dir verify/anchors/<YYYYMMDD>
```

该脚本会调用 `openssl ts -verify` 验证 FreeTSA 令牌；它证明该批次根在令牌时间点
已存在，但不证明事件内容真实。篡改任一字段、门禁摘要或重放旧报告都会使上述
校验失败。
