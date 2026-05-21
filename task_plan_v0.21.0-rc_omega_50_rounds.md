# MAREF Phase Ω: 50 轮自主递归演进全量补强方案

**计划日期**: 2026-05-10
**起始版本**: v0.20.0 GA (R80/D10/E7)
**目标版本**: v0.21.0 Final (R150)
**基线报告**: 《MAREF-世界Agent架构水平与能力边界补全评估报告-20260510》
**目标评分**: 7.42/10 → 8.7+/10

---

## 一、v0.20 GA 基线状态

### 现状总结

| 维度 | 评分 | 状态 |
|------|------|------|
| 治理状态机 | 10/10 | 全球碾压 |
| 形式化验证 | 10/10 | 独有 |
| 漂移检测 | 9/10 | 独有 |
| 红蓝对抗 | 9/10 | 独有 |
| 四级安全决策 | 9/10 | 领先 |
| Agent身份信任 | 7/10 | 独有 |
| 多Agent编排 | 7/10 | 追赶中 |
| A2A/MCP协议 | 7/10 | 跟随 |
| 可观测性 | 7/10 | 追赶中 |
| 桌面操控 | 5/10 | **核心短板** |
| 知识/记忆 | 5/10 | 追赶中 |
| 社区/生态 | 1/10 | **最大短板** |

### 19 项缺失编目 (来自评估报告)

**P0 (立即)**: INF-01多平台验证, FWK-01 A2A v0.3, APP-01真实桌面操控, ECO-01社区0基础, ECO-02 pip发布+文档
**P1 (中期)**: INF-02 GPU推理, INF-03 联邦Sidecar, FWK-02 24态, FWK-03 记忆三温, FWK-04 Trust抗操纵, APP-02 OpenCUA基准, APP-03 工作流模板, ECO-03 外部基准, ECO-04 企业部署
**P2 (长期)**: INF-04 Serverless, FWK-05 动态路由, APP-04 浏览器认证, APP-05 多模态, ECO-05 低代码适配, ECO-06 多语言SDK

### 代码基线

| 指标 | 值 |
|------|-----|
| Python 源文件 | 202 |
| 测试文件 | 136 |
| 测试数 | ~2,963 |
| 覆盖率 | 82.64% |
| 平台 | macOS only |

---

## 二、五大循环架构

```
v0.20.0 GA ──→ Phase Ω: 50 Rounds → v0.21.0 Final
              │
              ├── 循环1 (R101-R110): 操控闭环 — 解决 桌面操控 5/10 → 8/10
              ├── 循环2 (R111-R120): 平台覆盖 — 解决 macOS only → 三平台
              ├── 循环3 (R121-R130): 智能增强 — 解决 GPU/记忆/信任/社会态
              ├── 循环4 (R131-R140): 生态联通 — 解决 A2A v0.3/基准/Serverless
              └── 循环5 (R141-R150): 社区就绪 — 解决 0 stars → 500+ stars
```

### 每轮验收机制

每轮执行后自动运行:
1. `ruff check src/` — lint 零违规
2. `mypy src/` — typecheck 零错误
3. `pytest tests/ -x -q` — 回归零失败
4. 记录本轮变更文件数、新增/修改行数、测试增量

---

## 三、循环1: 操控闭环 (R101-R110)

### R101 | OmniParser 一键配置脚本 + 环境诊断升级

**目标**: `maref desktop setup` 自动检测→下载→配置模型
**补全缺口**: APP-01 (真实桌面操控)

**变更**:
- 新建 `scripts/setup_desktop.py`: 自动化 OmniParser 模型下载 + 配置
- 升级 `scripts/check_desktop_env.py`: 7 → 15 项检查
- CLI `maref desktop setup` 子命令

- [ ] `scripts/setup_desktop.py` — 模型下载/缓存/配置一键化
- [ ] `scripts/check_desktop_env.py` — 扩展至15项检查 (GPU/网络/安全/审计/浏览器)
- [ ] CLI: `maref desktop setup` 子命令
- [ ] 测试: `tests/cli/test_desktop_setup.py`
- [ ] Tag: v0.21.0-rc-r101

---

### R102 | PyAutoGUI 安全操控加固

**目标**: 12 种操作 + FAILSAFE + 权限诊断, 真实模式通过
**补全缺口**: APP-01

- [ ] `input_controller.py`: 添加操作速率限制 + 重试机制
- [ ] `input_controller.py`: 添加 `calibrate()` 屏幕尺寸自动检测
- [ ] `input_controller.py`: 添加 `safe_region` 边界框限制模式
- [ ] 测试: `tests/desktop/test_input_safety.py` +15 tests
- [ ] Tag: v0.21.0-rc-r102

---

### R103 | 环境诊断 7→15 项检查

**目标**: `maref check` 输出完整诊断报告
**补全缺口**: APP-01

- [ ] `scripts/check_desktop_env.py`: 新增8项检查
  - GPU 可用性 (torch.cuda / MPS)
  - 网络连通性 (HuggingFace CDN)
  - 磁盘空间 (模型下载区)
  - 安全审计日志状态
  - 浏览器 (Playwright Chromium)
  - 屏幕分辨率自适应
  - 多显示器检测
  - 沙箱模式状态
- [ ] JSON 输出模式 (`--json` flag)
- [ ] 测试: +10 tests
- [ ] Tag: v0.21.0-rc-r103

---

### R104 | 首次真实桌面任务端到端

**目标**: "打开浏览器→搜索→截图" 完整跑通, 成功率 > 85%
**补全缺口**: APP-01

- [ ] `desktop/agent.py`: 添加 `execute_task(task_description: str)` 高层接口
- [ ] `desktop/agent.py`: 添加操作超时 + 步骤级重试
- [ ] `scripts/desktop_demo_m1.py`: 升级为 `desktop_demo_e2e.py`
- [ ] 新增: `desktop/task_executor.py` — 任务→步骤序列映射器
- [ ] 测试: `tests/desktop/test_e2e_tasks.py` +10 tests
- [ ] Tag: v0.21.0-rc-r104

---

### R105 | ScreenParser 真实后端调优

**目标**: OmniParser real backend 延迟 < 500ms, 解析准确率 > 80%
**补全缺口**: APP-01, APP-02

- [ ] `screen_parser.py`: 添加 `benchmark()` 方法 (延迟 + 准确率)
- [ ] `screen_parser.py`: 添加图像预处理管线 (缩放/格式转换/批量)
- [ ] `screen_parser.py`: 添加 ONNX Runtime 推理可选路径
- [ ] 新增: `desktop/screen_parser_bench.py` — 30 张截图基准测试
- [ ] 测试: `tests/desktop/test_screen_parser_bench.py` +8 tests
- [ ] Tag: v0.21.0-rc-r105

---

### R106 | OpenCUA 22.6K 轨迹数据集集成

**目标**: 下载 + 预处理 + 基准跑通
**补全缺口**: APP-02

- [ ] 新增: `desktop/opencua_loader.py` — 数据集下载/解压/预处理
- [ ] 新增: `desktop/opencua_bench.py` — Action Accuracy 基准指标计算
- [ ] CLI: `maref desktop benchmark opencua`
- [ ] 测试: `tests/desktop/test_opencua.py` +12 tests
- [ ] Tag: v0.21.0-rc-r106

---

### R107 | DesktopAgent 自愈回路

**目标**: 操作失败 3 次自动切换策略
**补全缺口**: APP-01

- [ ] `desktop/agent.py`: 添加 `SelfHealingExecutor` 子组件
- [ ] `desktop/agent.py`: 3 种失败恢复策略: 重试→重新解析→降级到安全模式
- [ ] `desktop_governance.py`: OscillationRepair 与自愈回路联动
- [ ] 测试: `tests/desktop/test_self_healing.py` +15 tests
- [ ] Tag: v0.21.0-rc-r107

---

### R108 | 跨应用工作流基础模板库

**目标**: 5 个办公场景模板
**补全缺口**: APP-03

- [ ] 新增: `desktop/workflow_templates.py` — 工作流定义与序列化
- [ ] 5 个模板: 邮件撰写/表格编辑/浏览器表单/文件整理/终端命令
- [ ] 新增: `desktop/workflow_executor.py` — 模板→操作序列执行器
- [ ] 测试: `tests/desktop/test_workflows.py` +20 tests
- [ ] Tag: v0.21.0-rc-r108

---

### R109 | 浏览器认证会话管理

**目标**: Playwright persistent context + 加密状态持久化
**补全缺口**: APP-04

- [ ] `browser_controller.py`: 添加 `save_auth_state()` / `load_auth_state()`
- [ ] `browser_controller.py`: 添加 AES-256-GCM 加密的会话存储
- [ ] `browser_controller.py`: 添加 `login_workflow()` 基础认证流程
- [ ] 测试: `tests/desktop/test_browser_auth.py` +8 tests
- [ ] Tag: v0.21.0-rc-r109

---

### R110 | 操控闭环混沌验证

**目标**: 5 类故障注入 × 桌面操控, 恢复率 > 90%
**补全缺口**: APP-01 (最终验证)

- [ ] 新增: `tests/chaos/test_desktop_chaos.py` — 桌面专用混沌测试
- [ ] 5 类故障: PyAutoGUI timeout / OmniParser OOM / 窗口消失 / clipboard 锁定 / Playwright crash
- [ ] `agent.py`: 每类故障的自愈策略验证
- [ ] 恢复率统计报告
- [ ] Tag: v0.21.0-rc-r110

---

## 四、循环2: 平台覆盖 (R111-R120)

### R111 | Linux 屏幕捕获适配

**补全缺口**: INF-01

- [ ] `screen_capture.py`: 添加 `LinuxScreenCapture` (X11/Wayland 双后端)
- [ ] `screen_capture.py`: `auto_detect_backend()` 跨平台自动选择
- [ ] 截屏延迟 < 100ms
- [ ] 测试: `tests/desktop/test_screen_capture_linux.py` +10 tests
- [ ] Tag: v0.21.0-rc-r111

---

### R112 | Linux 键鼠操控适配

- [ ] `input_controller.py`: 添加 Linux 后端 (uinput/pynput)
- [ ] 12 操作全部通过验证
- [ ] 测试: `tests/desktop/test_input_linux.py` +10 tests
- [ ] Tag: v0.21.0-rc-r112

---

### R113 | Linux 窗口管理适配

- [ ] `window_manager.py`: 添加 Linux 后端 (xdotool/wmctrl)
- [ ] 6 种窗口操作全部通过
- [ ] 测试: `tests/desktop/test_window_linux.py` +8 tests
- [ ] Tag: v0.21.0-rc-r113

---

### R114 | Linux 全量测试通过

- [ ] `pytest tests/desktop/` Ubuntu 22.04 全部通过
- [ ] 338+ desktop tests 在 Linux 上验证
- [ ] Tag: v0.21.0-rc-r114

---

### R115 | Windows 屏幕捕获适配

- [ ] `screen_capture.py`: 添加 `WindowsScreenCapture` (DXGI/PyGetWindow)
- [ ] 截屏延迟 < 100ms
- [ ] 测试: `tests/desktop/test_screen_capture_win.py` +10 tests
- [ ] Tag: v0.21.0-rc-r115

---

### R116 | Windows 键鼠 + 窗口适配

- [ ] `input_controller.py`: Windows 后端 (win32api)
- [ ] `window_manager.py`: Windows 后端 (win32gui)
- [ ] 12 操作 + 6 窗口操作全部通过
- [ ] 测试: +15 tests
- [ ] Tag: v0.21.0-rc-r116

---

### R117 | Windows 全量测试通过

- [ ] `pytest tests/desktop/` Windows 11 全部通过
- [ ] Tag: v0.21.0-rc-r117

---

### R118 | 跨平台 CI 流水线

- [ ] `.github/workflows/ci.yml`: 添加 Linux + Windows runner
- [ ] 三平台矩阵: `[macos-latest, ubuntu-22.04, windows-2022]`
- [ ] 桌面测试标记隔离 (非桌面测试跨平台, 桌面测试条件执行)
- [ ] Tag: v0.21.0-rc-r118

---

### R119 | Docker 桌面操控容器

- [ ] `Dockerfile`: 添加 xvfb + Chromium + 桌面依赖
- [ ] `docker-compose.desktop.yml`: 桌面操控专用 compose
- [ ] Headless 桌面测试模式
- [ ] Tag: v0.21.0-rc-r119

---

### R120 | 多平台兼容性矩阵报告

- [ ] `scripts/platform_matrix.py`: 三平台 × 15 能力项自动检测
- [ ] 兼容性报告 JSON + Markdown 输出
- [ ] `docs/platform-compatibility.md` 自动生成
- [ ] Tag: v0.21.0-rc-r120

---

## 五、循环3: 智能增强 (R121-R130)

### R121 | GPU 推理管线

**补全缺口**: INF-02

- [ ] 新增: `maref/inference/` 包 (gpu_pipeline.py, onnx_backend.py, tensorrt_backend.py)
- [ ] `screen_parser.py`: GPU 推理可选路径 (MPS/CUDA)
- [ ] 视觉解析延迟 < 100ms (vs CPU 500ms+)
- [ ] 测试: `tests/unit/test_inference.py` +12 tests
- [ ] Tag: v0.21.0-rc-r121

---

### R122 | 记忆三温框架 — Hot 层

**补全缺口**: FWK-03

- [ ] `recursive/memory_three_temperature.py`: Hot 层实现
  - 短期向量记忆 (< 1h 生命周期)
  - LRU 淘汰策略
  - 与 LoRA 漂移检测联动
- [ ] 统一接口 `MemoryCell` 抽象类
- [ ] 测试: `tests/recursive/test_memory_hot.py` +15 tests
- [ ] Tag: v0.21.0-rc-r122

---

### R123 | 记忆三温框架 — Warm 层

- [ ] `recursive/memory_three_temperature.py`: Warm 层实现
  - 会话级向量记忆 (ChromaDB 后端)
  - 按 session_id 隔离
  - 语义相似度检索 (cosine top-k)
- [ ] 测试: `tests/recursive/test_memory_warm.py` +12 tests
- [ ] Tag: v0.21.0-rc-r123

---

### R124 | 记忆三温框架 — Cold 层

- [ ] `recursive/memory_three_temperature.py`: Cold 层实现
  - 长期事实检索
  - 知识图谱持久化 + 时间衰减
  - 跨会话知识融合
- [ ] 测试: `tests/recursive/test_memory_cold.py` +10 tests
- [ ] Tag: v0.21.0-rc-r124

---

### R125 | TrustScore 抗策略操纵 (Goodhart 检测)

**补全缺口**: FWK-04

- [ ] `identity/trust_engine.py`: 添加 Goodhart 检测
  - 行为-得分 Pearson 相关性追踪
  - 过度优化阈值告警 (r > 0.8)
- [ ] `identity/trust_engine.py`: 添加操纵尝试审计日志
- [ ] 测试: `tests/unit/test_trust_anti_gaming.py` +10 tests
- [ ] Tag: v0.21.0-rc-r125

---

### R126 | TrustScore 跨评估者方差检测

- [ ] `identity/trust_engine.py`: 添加多维度分歧检测
- [ ] 5 因子归一化后计算标准差
- [ ] 异常评分标记 (std > 0.3 → FLAG)
- [ ] 测试: `tests/unit/test_trust_variance.py` +8 tests
- [ ] Tag: v0.21.0-rc-r126

---

### R127 | Agent 社会性状态机 (10→18 态)

**补全缺口**: FWK-02

- [ ] `recursive/agent_24_state_machine.py`: 扩展至 18 态
- [ ] 新增 6 态: MARKET/NEGOTIATE/SANCTION/ALLIANCE/DELEGATE/EXILE
- [ ] 社会状态转换规则 (Gray Code)
- [ ] 测试: `tests/recursive/test_social_states.py` +15 tests
- [ ] Tag: v0.21.0-rc-r127

---

### R128 | 知识图谱多节点类型扩展

**补全缺口**: 知识 5→7

- [ ] `knowledge/`: 新增 4 种节点类型
  - EventNode (时间锚定的发生事件)
  - EntityNode (Agent/工具/模型实体)
  - ConceptNode (抽象概念与定义)
  - ProcedureNode (操作流程与步骤)
- [ ] 节点关系类型扩展 (7→12 种)
- [ ] 测试: `tests/knowledge/test_node_types.py` +12 tests
- [ ] Tag: v0.21.0-rc-r128

---

### R129 | LLM 动态路由成本优化

**补全缺口**: FWK-05

- [ ] `integration/gateway.py`: 添加多 Provider 价格感知
- [ ] 质量-成本帕累托选择器
- [ ] 实时 Provider 可用性健康检查
- [ ] 测试: `tests/integration/test_gateway_routing.py` +10 tests
- [ ] Tag: v0.21.0-rc-r129

---

### R130 | 智能增强集成混沌验证

- [ ] 新增: `tests/chaos/test_intelligence_chaos.py`
- [ ] 全链路 72h 稳定性: 记忆三温 + Trust + 社会态 + GPU
- [ ] 0 CB 误触发
- [ ] Tag: v0.21.0-rc-r130

---

## 六、循环4: 生态联通 (R131-R140)

### R131 | A2A v0.3 Bridge 升级

**补全缺口**: FWK-01

- [ ] `integration/a2a_bridge.py`: Signed Agent Cards 实现
  - JSON Web Proof (JWP) 签名格式
  - Agent Card 吊销列表
- [ ] `integration/a2a_bridge.py`: Task Handle v0.3 兼容
- [ ] 测试: `tests/integration/test_a2a_v0_3.py` +15 tests
- [ ] Tag: v0.21.0-rc-r131

---

### R132 | A2A 互操作验证

- [ ] `integration/a2a_bridge.py`: MAREF ↔ Google ADK Agent 互认
- [ ] Agent Card 交换 + 任务委托端到端
- [ ] 测试: `tests/integration/test_a2a_interop.py` +10 tests
- [ ] Tag: v0.21.0-rc-r132

---

### R133 | MCP Native 接口

- [ ] 新增: `maref/integration/mcp_server.py` — 原生 MCP Server
- [ ] 非 Bridge 翻译, 直接实现 MCP 协议
- [ ] Tool 注册/发现/调用 标准流程
- [ ] 测试: `tests/integration/test_mcp_native.py` +12 tests
- [ ] Tag: v0.21.0-rc-r133

---

### R134 | Dify/Coze 生产级适配器

**补全缺口**: ECO-05

- [ ] `sidecar/adapters/dify.py`: 从 mock 升级为真实平台集成
- [ ] 新增: `sidecar/adapters/coze.py` — 扣子平台适配器
- [ ] Agent 卡注册 + 治理注入
- [ ] 测试: `tests/sidecar/test_lowcode_adapters.py` +10 tests
- [ ] Tag: v0.21.0-rc-r134

---

### R135 | 外部基准: OSWorld

**补全缺口**: ECO-03

- [ ] 新增: `benchmarks/osworld_runner.py`
- [ ] OSWorld 150 计算机任务基准测试
- [ ] 与 Claude CU/OpenAI CUA 可比较分数
- [ ] 测试: `tests/benchmark/test_osworld.py` +8 tests
- [ ] Tag: v0.21.0-rc-r135

---

### R136 | 外部基准: GAIA

- [ ] 新增: `benchmarks/gaia_runner.py`
- [ ] L1/L2/L3 三级别结果报告
- [ ] 测试: `tests/benchmark/test_gaia.py` +8 tests
- [ ] Tag: v0.21.0-rc-r136

---

### R137 | 外部基准: SWE-bench Verified

- [ ] 新增: `benchmarks/swebench_runner.py`
- [ ] SWE-bench Verified 500 任务基准
- [ ] 测试: `tests/benchmark/test_swebench.py` +8 tests
- [ ] Tag: v0.21.0-rc-r137

---

### R138 | Serverless 运行时适配

**补全缺口**: INF-04

- [ ] 新增: `maref/serverless/` 包 (lambda_handler.py, cloudrun_handler.py)
- [ ] AWS Lambda / GCP Cloud Run 适配
- [ ] 冷启动 < 3s
- [ ] 测试: `tests/unit/test_serverless.py` +10 tests
- [ ] Tag: v0.21.0-rc-r138

---

### R139 | 跨集群 Sidecar 联邦

**补全缺口**: INF-03

- [ ] `sidecar/federation.py`: 联邦协调器
  - 节点发现 (mDNS/gossip)
  - 状态同步 (CRDT)
  - 任命 Leader
- [ ] `sidecar/federation.py`: RoundRobin/Weighted 负载均衡
- [ ] 测试: `tests/sidecar/test_federation.py` +15 tests
- [ ] Tag: v0.21.0-rc-r139

---

### R140 | 生态联通全链路验证

- [ ] 15 Agent 跨框架 (AutoGen/CrewAI/LangGraph/Dify/Coze) + A2A + MCP 全通过
- [ ] 3 外部基准结果可报告
- [ ] Tag: v0.21.0-rc-r140

---

## 七、循环5: 社区就绪 (R141-R150)

### R141 | `pip install maref` 三平台验证

**补全缺口**: ECO-02

- [ ] `pyproject.toml`: 三平台依赖检测
- [ ] `pip install maref[all]` macOS + Linux + Windows 全通过
- [ ] Wheel 构建 + 发布脚本: `scripts/release.sh`
- [ ] Tag: v0.21.0-rc-r141

---

### R142 | 一键安装脚本

- [ ] `install.sh`: `curl -sSL maref.dev/install | bash`
- [ ] 自动检测 OS → 安装 Python 依赖 → 下载模型
- [ ] 测试: macOS/Linux/Windows (通过 CI)
- [ ] Tag: v0.21.0-rc-r142

---

### R143 | MkDocs 文档站上线

- [ ] `mkdocs.yml`: 完整导航结构 (Home/Quickstart/Architecture/API/Security/Deploy/Community)
- [ ] `docs/`: 完善所有页面内容 + 代码示例
- [ ] `docs/api.md`: 完整 API 参考 (mkdocstrings 自动生成)
- [ ] GitHub Pages 部署 CI
- [ ] Tag: v0.21.0-rc-r143

---

### R144 | 3 个场景 Demo 视频脚本

- [ ] `docs/demos/desktop-control.md` — 桌面操控场景
- [ ] `docs/demos/agent-governance.md` — Agent 治理场景
- [ ] `docs/demos/sidecar-observation.md` — Sidecar 非侵入治理场景
- [ ] 录制脚本: `scripts/record_demos.sh`
- [ ] Tag: v0.21.0-rc-r144

---

### R145 | GitHub README 完整重写

**补全缺口**: ECO-01

- [ ] `README.md`: Stars-ready 展示页
  - 一句话定位: "Agent Governance OS"
  - 架构图 (Mermaid)
  - Demo GIF
  - 5 分钟 Quickstart
  - 竞品对比表格
  - 徽章: CI/coverage/PyPI/Python/License
- [ ] Tag: v0.21.0-rc-r145

---

### R146 | 企业级部署文档

**补全缺口**: ECO-04

- [ ] `docs/deployment/kubernetes.md` — K8s 部署指南
- [ ] `docs/deployment/docker.md` — Docker 部署
- [ ] `docs/deployment/bare-metal.md` — 裸机部署
- [ ] `docs/security/production-hardening.md` — 生产加固清单
- [ ] Tag: v0.21.0-rc-r146

---

### R147 | 企业参考架构案例

- [ ] `docs/case-studies/agent-cluster-governance.md` — Agent 集群治理
- [ ] `docs/case-studies/desktop-automation.md` — 桌面自动化
- [ ] `docs/case-studies/compliance-audit.md` — 安全合规审计
- [ ] Tag: v0.21.0-rc-r147

---

### R148 | TypeScript SDK 基础版

**补全缺口**: ECO-06

- [ ] 新建: `sdk/typescript/` — npm 包 `@maref/sdk`
- [ ] 治理状态查询 API
- [ ] CircuitBreaker 事件订阅 (WebSocket)
- [ ] 审计日志查询
- [ ] 测试: Vitest 测试套件
- [ ] Tag: v0.21.0-rc-r148

---

### R149 | GitHub 社区基础设施

- [ ] `.github/ISSUE_TEMPLATE/` — Bug Report + Feature Request
- [ ] `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] `.github/CODEOWNERS`
- [ ] `.github/CONTRIBUTING.md` — 贡献者指南
- [ ] `CODE_OF_CONDUCT.md` — 社区行为准则
- [ ] CI badge: `[![CI](https://github.com/...)]`
- [ ] Tag: v0.21.0-rc-r149

---

### R150 | Omega 全量验收

- [ ] 全量 pytest (预期 4200+ tests)
- [ ] `coverage report --fail-under=88`
- [ ] `ruff check src/` 零违规
- [ ] `mypy src/` 零错误
- [ ] 50+ Agent 集群 48h 稳定性
- [ ] `pyproject.toml`: version = "0.21.0"
- [ ] `CHANGELOG.md`: Phase Ω 50 轮完整记录
- [ ] git tag: v0.21.0-final
- [ ] 综合评分 ≥ 8.7/10
- [ ] Tag: v0.21.0-final

---

## 八、50 轮汇总表

| 轮次 | 循环 | 核心动作 | 补全缺口 | 预期测试增量 |
|------|------|----------|---------|------------|
| R101 | 操控闭环 | OmniParser 一键配置 | APP-01 | +5 |
| R102 | 操控闭环 | PyAutoGUI 安全加固 | APP-01 | +15 |
| R103 | 操控闭环 | 环境诊断 15 项 | APP-01 | +10 |
| R104 | 操控闭环 | 首次真实桌面任务 | APP-01 | +10 |
| R105 | 操控闭环 | ScreenParser 调优 | APP-01/02 | +8 |
| R106 | 操控闭环 | OpenCUA 基准集成 | APP-02 | +12 |
| R107 | 操控闭环 | 自愈回路 | APP-01 | +15 |
| R108 | 操控闭环 | 工作流模板库 | APP-03 | +20 |
| R109 | 操控闭环 | 浏览器认证会话 | APP-04 | +8 |
| R110 | 操控闭环 | 操控混沌验证 | APP-01 | +12 |
| R111 | 平台覆盖 | Linux 屏幕捕获 | INF-01 | +10 |
| R112 | 平台覆盖 | Linux 键鼠适配 | INF-01 | +10 |
| R113 | 平台覆盖 | Linux 窗口管理 | INF-01 | +8 |
| R114 | 平台覆盖 | Linux 全量验证 | INF-01 | 0 |
| R115 | 平台覆盖 | Windows 屏幕捕获 | INF-01 | +10 |
| R116 | 平台覆盖 | Windows 键鼠+窗口 | INF-01 | +15 |
| R117 | 平台覆盖 | Windows 全量验证 | INF-01 | 0 |
| R118 | 平台覆盖 | 跨平台 CI | INF-01 | +5 |
| R119 | 平台覆盖 | Docker 桌面容器 | INF-01 | +5 |
| R120 | 平台覆盖 | 平台兼容矩阵 | INF-01 | +5 |
| R121 | 智能增强 | GPU 推理管线 | INF-02 | +12 |
| R122 | 智能增强 | 记忆三温 Hot | FWK-03 | +15 |
| R123 | 智能增强 | 记忆三温 Warm | FWK-03 | +12 |
| R124 | 智能增强 | 记忆三温 Cold | FWK-03 | +10 |
| R125 | 智能增强 | Trust 抗操纵 | FWK-04 | +10 |
| R126 | 智能增强 | Trust 跨评估方差 | FWK-04 | +8 |
| R127 | 智能增强 | 社会性状态机 18态 | FWK-02 | +15 |
| R128 | 智能增强 | 知识图谱多类型 | 知识 | +12 |
| R129 | 智能增强 | LLM 动态路由 | FWK-05 | +10 |
| R130 | 智能增强 | 智能混沌验证 | ALL | +10 |
| R131 | 生态联通 | A2A v0.3 | FWK-01 | +15 |
| R132 | 生态联通 | A2A 互操作 | FWK-01 | +10 |
| R133 | 生态联通 | MCP Native | P2-MCP | +12 |
| R134 | 生态联通 | Dify/Coze 适配 | ECO-05 | +10 |
| R135 | 生态联通 | OSWorld 基准 | ECO-03 | +8 |
| R136 | 生态联通 | GAIA 基准 | ECO-03 | +8 |
| R137 | 生态联通 | SWE-bench | ECO-03 | +8 |
| R138 | 生态联通 | Serverless 适配 | INF-04 | +10 |
| R139 | 生态联通 | Sidecar 联邦 | INF-03 | +15 |
| R140 | 生态联通 | 全链路验证 | ALL | +5 |
| R141 | 社区就绪 | pip 三平台验证 | ECO-02 | +5 |
| R142 | 社区就绪 | 一键安装脚本 | ECO-02 | +5 |
| R143 | 社区就绪 | 文档站上线 | ECO-02 | 0 |
| R144 | 社区就绪 | Demo 视频脚本 | ECO-01 | 0 |
| R145 | 社区就绪 | README 重写 | ECO-01 | 0 |
| R146 | 社区就绪 | 企业部署文档 | ECO-04 | 0 |
| R147 | 社区就绪 | 企业参考案例 | ECO-04 | 0 |
| R148 | 社区就绪 | TypeScript SDK | ECO-06 | +15 |
| R149 | 社区就绪 | 社区基础设施 | ECO-01 | 0 |
| R150 | 社区就绪 | Omega 全量验收 | ALL | 0 |
| **合计** | — | — | **19/19 缺口** | **~+1,200** |

---

## 九、最终交付物 (R150 完成时)

| 指标 | v0.20 GA (当前) | v0.21 Final (目标) |
|------|----------------|-------------------|
| Python 源文件 | 202 | ~260 |
| 测试文件 | 136 | ~180 |
| 总测试 | ~2,963 | ~4,200+ |
| 代码行数 | ~42,500 | ~55,000+ |
| 覆盖率 | 82.64% | ~88% |
| 综合评分 | 7.42/10 | **8.7+/10** |
| 治理状态机 | 10/10 | 10/10 (保持) |
| 形式化验证 | 10/10 | 10/10 (保持) |
| 桌面操控 | 5/10 | **8/10** |
| 平台覆盖 | macOS | **macOS/Linux/Windows** |
| A2A 协议 | v0.2.6 | **v0.3 Signed Cards** |
| 记忆三温 | ❌ | **✅ Hot/Warm/Cold** |
| Trust 抗操纵 | ❌ | **✅ Goodhart 检测** |
| 社会性状态机 | 10 态 | **18 态 (10→18)** |
| GPU 推理 | ❌ | **✅ ONNX/TensorRT** |
| 外部基准 | ❌ | **OSWorld/GAIA/SWE-bench** |
| Serverless | ❌ | **✅ Lambda/Cloud Run** |
| npm SDK | ❌ | **✅ @maref/sdk v0.1** |
| pip install | ✅ | ✅ (三平台验证) |
| 社区 | 0 stars | **500+ stars** |
| 文档站 | ❌ | **✅ docs.maref.dev** |