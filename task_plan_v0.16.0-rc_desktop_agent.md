# MAREF v0.16.0-rc: 桌面 Agent 治理桥接 10 轮实施方案

**计划日期**: 2026-05-09
**起始版本**: v0.15.0-rc (R80)
**目标版本**: v0.16.0-rc (D10)
**范围**: M1 (视觉操控原子层 MVP) + M2 (安全门集成)

---

## 一、版本路线

```
v0.15.0-rc (R80) ──→ D1-D10 → v0.16.0-rc
                              ├── M1: D1-D5 (视觉操控原子层 MVP)
                              └── M2: D6-D10 (安全门 + 治理集成)
```

---

## 二、D1: 环境搭建 + 开源评估

| 任务 | 交付物 |
|------|--------|
| OmniParser 集成基准骨架 | `desktop/screen_parser.py` 框架 + OmniParser 接口抽象 |
| PyAutoGUI 安全包装层 | `desktop/input_controller.py` 安全原语定义 |
| OpenCUA 数据集评估 | `desktop/` 包结构 + 测试基础设施 |
| 技术选型报告 | 依赖可用性确认 + 架构决策记录 |

- [ ] desktop 包初始化
- [ ] 测试基础设施
- [ ] OmniParser 接口定义
- [ ] PyAutoGUI 安全评估
- [ ] Tag: v0.16.0-rc-d1

---

## 三、D2: screen_capture.py + screen_parser.py

- [ ] CGDisplay 截图捕获 + 可配置降采样
- [ ] 敏感区域脱敏
- [ ] OmniParser 集成: 截屏 → 结构化 UI 元素 JSON
- [ ] 15+ tests
- [ ] Tag: v0.16.0-rc-d2

---

## 四、D3: input_controller.py + window_manager.py

- [ ] 键鼠原子操作: 点击/双击/右键/拖拽/文本输入/快捷键
- [ ] 操作前 SafetyGate 预检
- [ ] macOS Accessibility API: 窗口列表/聚焦/切换/区域截图
- [ ] 20+ tests
- [ ] Tag: v0.16.0-rc-d3

---

## 五、D4: verification.py + clipboard.py

- [ ] 操作后截图对比 (PIL + SSIM)
- [ ] 状态检查 + 失败原因分类
- [ ] 剪贴板读写 + 安全过滤
- [ ] 15+ tests
- [ ] Tag: v0.16.0-rc-d4

---

## 六、D5: M1 最小闭环集成

- [ ] 截图→解析→操作→验证 端到端流水线
- [ ] 仅 macOS + 预定义安全应用列表
- [ ] 演示脚本: scripts/desktop_demo_m1.py
- [ ] 10+ tests
- [ ] Tag: v0.16.0-rc-d5

---

## 七、D6-D10: M2 安全门集成（待 D5 完成后细化）

