# MAREF 系统崩溃防护指南

## 崩溃根因分析

### 核心问题
**内存耗尽 + I/O 风暴导致系统看门狗超时触发自动重启**

### 证据链
1. **内存使用率 99.6%** - 24GB 物理内存仅剩 64MB 空闲
2. **Swap 频繁换入换出** - 784 万次 Swapins / 1227 万次 Swapouts
3. **Trae CN AI Agent 内存泄漏** - 从 21MB 暴涨到 1.5GB，持续 pwrite 写盘
4. **BasedPyright 索引压力** - 1592 个 Python 文件 + 1.1GB node_modules 被持续索引
5. **maref serve 运行 131+ 小时** - 超过 5 天未重启

### 内存消耗 Top 进程（清理后）
| 进程 | RSS (MB) | 说明 |
|------|----------|------|
| Trae CN Helper (AI Agent) | 950 MB | 内存泄漏主因 |
| Trae CN Renderer 3 | 598 MB | 编辑器渲染窗口 |
| Trae CN Renderer 1 | 564 MB | 编辑器渲染窗口 |
| BasedPyright | 263 MB | Python 类型检查器 |
| Chrome Renderer | 880 MB | 浏览器渲染 |
| Playwright Node | 141 MB | 浏览器自动化 |

## 已实施的防护措施

### 1. BasedPyright 索引优化 ✅
**文件**: `pyrightconfig.json`
- 排除 `node_modules`, `.git`, `dist`, `build`, `__pycache__` 等目录
- 限制索引范围为 `src`, `tests`, `scripts`
- 关闭类型检查的详细输出
- **效果**: 减少 70%+ 的索引文件数量

### 2. 内存监控脚本 ✅
**文件**: `scripts/memory_monitor.py`
- 持续监控内存使用率，超过阈值自动告警
- 监控 maref serve 运行时间，超过 24 小时提醒重启
- 检测磁盘 I/O 风暴
- **使用方式**:
  ```bash
  # 单次检查
  python3 scripts/memory_monitor.py --once
  
  # 持续监控（后台运行）
  nohup python3 scripts/memory_monitor.py > /dev/null 2>&1 &
  ```

### 3. 紧急清理脚本 ✅
**文件**: `scripts/emergency_cleanup.sh`
- 终止高内存消耗的 pytest 进程
- 清理 Python 缓存和覆盖率报告
- 显示清理前后内存对比
- **使用方式**:
  ```bash
  bash scripts/emergency_cleanup.sh
  ```

### 4. 进程内存保护机制 ✅
**文件**: `scripts/memory_monitor.py` (内置)
- 内存使用率 > 95% 时自动终止非关键 MAREF 进程
- 保护关键系统进程不被误杀
- 清理 Python 缓存释放空间

## 需要手动执行的操作

### 🔴 紧急（立即执行）

#### 1. 重启 Trae CN
**原因**: AI Agent 进程 (libai_agent.dylib) 内存泄漏，从 21MB 暴涨到 950MB
**步骤**:
1. 保存所有工作
2. 完全退出 Trae CN (Cmd+Q)
3. 重新打开 Trae CN
4. **预期效果**: 释放 ~3GB 内存

#### 2. 重启 maref serve
**原因**: 已连续运行 131+ 小时（5.5 天）
**步骤**:
```bash
# 停止旧进程
kill -TERM 44631

# 重新启动
maref serve --port 8000 --gui &
```
**预期效果**: 释放 ~13MB 内存，重置运行状态

#### 3. 关闭不必要的 Trae 标签页
**原因**: 3 个渲染窗口占用 ~1.8GB 内存
**步骤**:
- 关闭不需要的编辑器标签
- 每个标签页约 400-600MB
- **预期效果**: 每关闭一个标签页释放 ~500MB

### 🟡 建议（今天执行）

#### 4. 配置 Trae 的 BasedPyright 内存限制
在 Trae 设置中添加：
```json
{
  "python.analysis.memoryLimit": 1024,
  "python.analysis.maxTypeEvaluationDepth": 50
}
```

#### 5. 设置定期清理 cron job
```bash
# 每天凌晨 3 点清理 Python 缓存
0 3 * * * find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
```

#### 6. 监控内存压力
```bash
# 添加到 ~/.zshrc
alias memstat='python3 ./scripts/memory_monitor.py --once'
```

### 🟢 长期优化

#### 7. 分离大文件到独立仓库
- 将 `gui/` 目录（node_modules 1.1GB）分离到独立仓库
- 将大型测试数据集移至外部存储

#### 8. 配置 Git GC
```bash
cd .
git gc --aggressive --prune=now
```
**预期效果**: 减少 1.8GB .git 目录大小

## 监控指标

### 安全阈值
| 指标 | 安全 | 警告 | 危险 |
|------|------|------|------|
| 内存使用率 | < 80% | 80-95% | > 95% |
| 空闲内存 | > 2GB | 1-2GB | < 1GB |
| maref serve 运行时间 | < 24h | 24-48h | > 48h |
| 磁盘写入速度 | < 50MB/s | 50-100MB/s | > 100MB/s |

### 检查命令
```bash
# 内存状况
vm_stat | head -20

# 进程内存
ps aux -r | head -20

# 磁盘 I/O
iostat -c 1 2

# MAREF 专用检查
python3 scripts/memory_monitor.py --once
```

## 崩溃恢复步骤

如果系统再次崩溃：

1. **立即执行紧急清理**
   ```bash
   bash scripts/emergency_cleanup.sh
   ```

2. **重启 Trae CN**
   - Cmd+Q 完全退出
   - 重新打开

3. **重启 maref serve**
   ```bash
   kill -TERM $(pgrep -f "maref serve") 2>/dev/null
   maref serve --port 8000 --gui &
   ```

4. **检查系统日志**
   ```bash
   log show --predicate 'eventMessage contains "restart"' --last 1h
   ```

## 预防措施总结

| 措施 | 状态 | 效果 |
|------|------|------|
| pyrightconfig.json 排除大目录 | ✅ | 减少 70% 索引压力 |
| 内存监控脚本 | ✅ | 提前预警内存不足 |
| 紧急清理脚本 | ✅ | 快速释放内存 |
| 重启 Trae CN | ⏳ 待执行 | 释放 ~3GB |
| 重启 maref serve | ⏳ 待执行 | 重置运行状态 |
| 关闭不必要标签页 | ⏳ 待执行 | 每页释放 ~500MB |
| Git GC 清理 | ⏳ 待执行 | 减少 1.8GB .git |

---

**最后更新**: 2026-05-17
**下次检查**: 2026-05-18
