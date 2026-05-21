# MAREF 备份策略

> 版本: v0.25.0-rc
> 最后更新: 2026-05-20

---

## 1. 备份范围

| 类别 | 内容 | 优先级 | 备份方式 |
|------|------|--------|---------|
| JSON 数据存储 | Agent 状态、治理决策记录、审计日志 | P0 | 全量 + 增量 |
| 配置文件 | `.env`, `config.yaml`, 特征配置 | P0 | 全量 |
| 知识图谱 (KG) | 知识库索引、嵌入向量 | P1 | 全量 |
| 测试数据 | 测试夹具、模拟数据 | P2 | 全量 |
| 日志文件 | 应用日志、审计日志归档 | P1 | 增量 |

### 排除项
- 临时文件 `/tmp/*`, `.pyc` 缓存
- `node_modules/`, `__pycache__/`
- Git 仓库自身（由 Git 备份策略覆盖）
- 运行时生成的大文件（> 1GB）

---

## 2. 备份策略

### 2.1 全量备份

执行完整的数据快照，包含所有指定目录的全部内容。

- **频率**: 每日 02:00 UTC
- **保留**: 最近 7 个每日全量备份
- **命令**: `bash scripts/backup.sh --mode full`
- **命名**: `maref-backup-full-{YYYYMMDD}-{HHMMSS}.tar.gz`
- **存储路径**: `<BACKUP_ROOT>/daily/`

### 2.2 增量备份

仅备份自上次全量备份以来修改过的文件。

- **频率**: 每 6 小时（06:00 / 12:00 / 18:00 / 22:00 UTC）
- **保留**: 所有增量在下次全量备份时合并
- **命令**: `bash scripts/backup.sh --mode incremental`
- **命名**: `maref-backup-inc-{YYYYMMDD}-{HHMMSS}.tar.gz`
- **存储路径**: `<BACKUP_ROOT>/incremental/`

### 2.3 保留周期

| 备份类型 | 保留时间 | 最大数量 |
|---------|---------|:--------:|
| 日备（全量） | 7 天 | 7 |
| 周备（全量） | 4 周 | 4 |
| 月备（全量） | 6 个月 | 6 |
| 增量备份 | 至下次全量 | - |

### 2.4 清理规则

备份清理自动执行以下规则：

1. 日备：保留最近 7 天，超出则删除
2. 周备：仅保留最近 4 个周日备份（通过 `--weekly` 标记识别）
3. 月备：仅保留最近 6 个月末备份（通过 `--monthly` 标记识别）
4. 增量：保留自上次全量以来的所有增量

---

## 3. 恢复目标

| 指标 | 目标值 | 测量方式 |
|------|--------|---------|
| RTO (Recovery Time Objective) | ≤ 30 分钟 | 从灾难发生到系统完全恢复的时间 |
| RPO (Recovery Point Objective) | ≤ 24 小时 | 灾难发生时可能丢失的最大数据时间窗口 |
| 备份验证 | 每次备份后自动验证 | 校验 tarball 完整性和文件数量 |

### 3.1 RTO 分解

| 阶段 | 预计耗时 | 说明 |
|------|---------|------|
| 灾难检测 | 2 分钟 | 监控告警或人工发现 |
| 备份定位 | 1 分钟 | 选择最近的可用备份 |
| 数据恢复 | 15 分钟 | 解压并恢复数据到目标目录 |
| 服务启动 | 5 分钟 | 启动 MAREF 服务 |
| 完整性验证 | 5 分钟 | 运行验证检查 |
| 流量切换 | 2 分钟 | 恢复对外服务 |
| **总计** | **≤ 30 分钟** | |

### 3.2 RPO 保障

- 全量备份每日一次 → 最大数据丢失 < 24 小时
- 增量备份每 6 小时一次 → 典型数据丢失 < 6 小时
- 关键审计日志实时落盘，不依赖备份

---

## 4. 备份验证流程

每次备份完成后自动执行以下验证步骤：

### 4.1 完整性检查

```bash
# 验证 tarball 可正常解压
tar -tzf maref-backup-full-20260520-020000.tar.gz > /dev/null && echo "PASS: archive integrity"

# 验证文件数量不为零
tar -tzf maref-backup-full-20260520-020000.tar.gz | wc -l | grep -v "^0$" && echo "PASS: non-empty backup"
```

### 4.2 内容检查

- 确认必要目录（`data/`, `config/`, `logs/`）存在于备份中
- 确认关键文件（`config.yaml` 等）存在于备份中
- 确认备份大小大于最小阈值（100KB）

### 4.3 自动化验证脚本

备份脚本内置 `--verify` 模式，自动执行上述检查：

```bash
bash scripts/backup.sh --mode full --verify
```

---

## 5. 灾难恢复流程

### 5.1 恢复步骤

1. **停止当前服务**
   ```bash
   systemctl stop maref
   ```

2. **定位备份**
   ```bash
   ls -la <BACKUP_ROOT>/daily/ | tail -5
   ```

3. **执行恢复**
   ```bash
   bash scripts/backup.sh --mode restore --backup-file <path-to-backup>
   ```

4. **启动服务**
   ```bash
   systemctl start maref
   systemctl status maref
   ```

5. **验证恢复**
   ```bash
   curl -f http://localhost:8080/health
   python -m pytest tests/chaos/test_disaster_recovery.py -v
   ```

### 5.2 回滚方案

如果恢复后系统异常：

1. 回滚至上一次备份：`bash scripts/backup.sh --mode restore --backup-file <previous-backup>`
2. 如果所有备份均异常，使用 Git 重新部署：
   ```bash
   git checkout <last-known-good-tag>
   pip install -e ".[dev]"
   ```

---

## 6. 备份目录结构

```
<BACKUP_ROOT>/
├── daily/
│   ├── maref-backup-full-20260513-020000.tar.gz
│   ├── maref-backup-full-20260514-020000.tar.gz
│   ├── maref-backup-full-20260515-020000.tar.gz
│   └── ... (最近 7 天)
├── weekly/
│   ├── maref-backup-full-20260427-020000.tar.gz
│   ├── maref-backup-full-20260504-020000.tar.gz
│   ├── maref-backup-full-20260511-020000.tar.gz
│   └── maref-backup-full-20260518-020000.tar.gz (最近 4 周)
├── monthly/
│   ├── maref-backup-full-20251130-020000.tar.gz
│   ├── maref-backup-full-20251231-020000.tar.gz
│   └── ... (最近 6 个月)
└── incremental/
    ├── maref-backup-inc-20260520-060000.tar.gz
    ├── maref-backup-inc-20260520-120000.tar.gz
    ├── maref-backup-inc-20260520-180000.tar.gz
    └── maref-backup-inc-20260520-220000.tar.gz
```

---

## 7. 备份配置

可以通过环境变量配置备份行为：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAREF_BACKUP_ROOT` | `./backups` | 备份存储根目录 |
| `MAREF_BACKUP_RETENTION_DAILY` | `7` | 日备保留天数 |
| `MAREF_BACKUP_RETENTION_WEEKLY` | `4` | 周备保留周数 |
| `MAREF_BACKUP_RETENTION_MONTHLY` | `6` | 月备保留月数 |
| `MAREF_BACKUP_VERIFY` | `true` | 是否自动验证 |

---

## 8. 附录

### 8.1 备份合规性

| 要求 | 合规状态 | 说明 |
|------|---------|------|
| ISO 27001 A.12.3.1 | ✓ | 备份策略已定义并实施 |
| ISO 27001 A.12.3.2 | ✓ | 备份定期验证 |
| ISO 27001 C.5.33 | ✓ | 审计日志保护 |
| SOC 2 CC7.1 | ✓ | 备份恢复测试 |
| SOC 2 CC7.2 | ✓ | 灾难恢复计划 |