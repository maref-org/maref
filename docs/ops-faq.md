# MAREF 运维知识库 — 常见问题处理 (FAQ)

## 安装与部署

### Q: 安装依赖时提示 `percv` 找不到

**原因**: `percv` 是可选依赖，通过本地路径引用 (`tool.uv.sources`)。

**解决方案**:
```bash
# 如果不需要 percv 功能，跳过即可
pip install -e ".[dev]" --no-deps
pip install pytest pytest-asyncio pytest-cov ruff mypy

# 如果需要 percv，确保 autoresearch/percv 目录存在
ls ../autoresearch/percv
```

### Q: Tauri 构建失败

**原因**: 缺少 Rust 工具链或系统依赖。

**解决方案**:
```bash
# 安装 Rust
rustup update

# macOS: 安装系统依赖
xcode-select --install

# Linux: 安装系统依赖
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

### Q: Sidecar 服务端口被占用

**原因**: 默认端口 8000 已被其他进程占用。

**解决方案**:
```bash
# 查找占用进程
lsof -i :8000
# 终止占用进程
kill -9 <PID>
# 或使用其他端口
PORT=8001 python -m src.sidecar.server
```

## 测试与质量

### Q: 测试收集错误 (ERROR Collection)

**原因**: `sidecar/` 等根目录包污染导致命名空间冲突。

**解决方案**:
```bash
# 检查是否存在根目录 sidecar/
ls -d sidecar/ 2>/dev/null

# 如果存在且不是 git 跟踪的，删除它
git status sidecar/
rm -rf sidecar/
```

### Q: macOS 测试失败 (skipif 未生效)

**原因**: 某些测试需要 macOS Accessibility 权限。

**解决方案**: macOS 非 GUI 环境（如 CI）下这些测试会自动跳过。如需本地运行：
```bash
# 在系统设置中授予 Terminal/Accessibility 权限
# 或使用 xvfb (Linux)
```

### Q: 覆盖率低于 70%

**原因**: 新功能缺少测试覆盖。

**解决方案**:
```bash
# 查看未覆盖的行
coverage report --show-missing

# 生成 HTML 报告并查看
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## CI/CD

### Q: CI 中的 LHCI (Lighthouse) 步骤失败

**原因**: 前端性能未达到预算标准。

**解决方案**:
1. 运行本地 LHCI：`cd gui && pnpm lhci autorun --config=../lighthouserc.json`
2. 查看性能报告中的具体指标
3. 优化关键指标（LCP、CLS、TBT 等）
4. 如确认为误报，调整 `lighthouserc.json` 中的阈值

### Q: cargo-audit 检测到 Rust 依赖漏洞

**原因**: Rust 依赖存在已知漏洞。

**解决方案**:
```bash
# 更新 Cargo.lock
cd gui/src-tauri
cargo update

# 如果漏洞在直接依赖中，升级到修复版本
cargo upgrade <package-name>

# 如果漏洞在间接依赖中且无法立即修复，暂时忽略
# cargo audit --ignore <RUSTSEC-ID>
```

### Q: release-check.sh 失败

**原因**: 某个门禁检查未通过。

**解决方案**:
```bash
# 手动运行检查脚本查看具体失败项
bash scripts/release-check.sh

# 逐项修复后重新运行
```

## 监控与告警

### Q: 如何查看当前告警状态

**解决方案**:
```bash
# 检查 sidecar 健康状态
curl -s http://localhost:8000/health | python -m json.tool

# 查看 Prometheus 指标
curl -s http://localhost:8000/metrics | grep -E "maref_|governance_"

# 查看审计日志
python -m maref audit show --last 20
```

### Q: 如何配置告警通知

**解决方案**: 当前告警通过 GitHub Issues 跟踪。如需配置外部通知：
1. 配置 Prometheus + Alertmanager
2. 在 `alertmanager.yml` 中添加通知渠道（Slack、Email 等）
3. 关联告警名称与 Runbook（见 [Runbook 目录](runbook/README.md)）

## 发布流程

### Q: 发布前需要做哪些检查

**解决方案**:
1. 运行 `bash scripts/release-check.sh` 完成自动检查
2. 确认 CHANGELOG.md 已更新
3. 确认 `pyproject.toml` 和 `gui/src-tauri/Cargo.toml` 版本号同步
4. 确认所有 CI Pipeline 通过
5. 根据发布类型查阅 [发布审批矩阵](release-approval-matrix.md)

### Q: 发布后如何监控

**解决方案**: 按照 [发布后监控检查清单](post-release-monitoring-checklist.md) 在 T+1h、T+24h、T+7d、T+30d 执行检查。

### Q: 紧急修复 (Hotfix) 流程

**解决方案**:
1. 创建 hotfix 分支：`git checkout -b hotfix/<issue-description>`
2. 修复问题并提交
3. 跳过完整 CI（仅运行关键测试）：`pytest tests/unit tests/security`
4. 合并到 main 并打 tag：`git tag v0.26.1`
5. 24 小时内补充审计和完整测试