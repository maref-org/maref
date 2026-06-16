# MAREF 混沌测试场景库

> 版本: v0.25.0-rc
> 场景数: 12
> 覆盖类别: 网络 / 存储 / 计算 / 组合

---

## 场景 1: 网络延迟注入

| 属性 | 值 |
|------|-----|
| 场景名称 | Network Latency Injection |
| 故障类型 | Network |
| 故障大类 | 网络 |

**描述**: 向 Agent 间通信链路注入可配置的网络延迟，模拟跨区域部署或网络拥堵场景。

**注入参数**:
- `latency_ms`: 延迟毫秒数（默认 500ms，范围 100-10000）
- `host`: 目标主机
- `port`: 目标端口

**预期系统行为**:
- Sidecar 观测到 Agent 心跳超时
- GovernanceOverlay 检测到多个 Agent 进入 WAITING 状态
- DeadlockDetector 在 stuck_threshold_seconds 后触发死锁告警
- 系统不应进入 HALT 状态，应保持在 STABILIZE 或 ACT 状态

**验证方式**:
- 确认 FaultEvent.action == "inject" 且 success == True
- 确认 Monitor 输出中包含 network_latency 相关告警
- 确认系统在延迟结束后自动恢复

---

## 场景 2: 网络分区

| 属性 | 值 |
|------|-----|
| 场景名称 | Network Partition |
| 故障类型 | Network |
| 故障大类 | 网络 |

**描述**: 模拟 Agent 群体被划分为多个网络分区，分区之间完全隔离，分区内部可正常通信。

**注入参数**:
- `partition_count`: 分区数量（默认 2）
- `partition_duration_s`: 分区持续时间（默认 30s）
- `drop_rate`: 丢包率（默认 1.0，即完全隔离）

**预期系统行为**:
- 跨分区 Agent 通信全部超时
- GovernanceOverlay 检测到分区内 Agent 数量减少
- 部分 Agent 状态变为 UNKNOWN 或 LOST
- 系统应触发 EmergencyHalt 或进入 STABILIZE 状态

**验证方式**:
- 确认 ChaosPlan 中记录分区事件
- 确认分区期间跨分区消息全部失败
- 确认网络恢复后分区 Agent 重新加入集群

---

## 场景 3: 磁盘空间耗尽

| 属性 | 值 |
|------|-----|
| 场景名称 | Disk Space Exhaustion |
| 故障类型 | DISK |
| 故障大类 | 存储 |

**描述**: 模拟磁盘空间被占满，导致日志写入、数据持久化和状态存储失败。

**注入参数**:
- `space_mb`: 占用磁盘空间大小（默认 100MB）
- `corrupt`: 是否同时执行文件损坏（默认 False）
- `target_dir`: 目标目录路径

**预期系统行为**:
- 日志系统写入失败，抛出 IOError
- 状态持久化操作返回错误
- AuditLogger 无法写入新的审计记录
- 系统触发磁盘告警并尝试清理临时文件

**验证方式**:
- 确认 DISK 类型故障注入成功
- 确认相关 IO 操作返回预期的错误码
- 确认磁盘空间释放后系统恢复正常

---

## 场景 4: 磁盘 I/O 高负载

| 属性 | 值 |
|------|-----|
| 场景名称 | Disk IO Pressure |
| 故障类型 | DISK |
| 故障大类 | 存储 |

**描述**: 通过大量并发读写操作模拟磁盘 I/O 高负载，测试系统在 I/O 瓶颈下的行为。

**注入参数**:
- `io_threads`: 并发 I/O 线程数（默认 4）
- `io_duration_s`: 持续时长（默认 15s）
- `block_size_kb`: 每次读写块大小（默认 1024KB）

**预期系统行为**:
- KV 存储读写延迟显著增加
- Agent 状态更新变慢
- GovernanceOverlay 观测周期变长
- 系统应在 I/O 负载降低后恢复正常延迟

**验证方式**:
- 确认操作延迟在注入期间明显高于基线
- 确认 I/O 负载结束后延迟恢复到基线水平
- 确认没有数据损坏或丢失

---

## 场景 5: CPU 过载

| 属性 | 值 |
|------|-----|
| 场景名称 | CPU Overload |
| 故障类型 | CPU |
| 故障大类 | 计算 |

**描述**: 通过密集计算任务占用 CPU 资源，模拟 CPU 过载对系统的影响。

**注入参数**:
- `load_pct`: CPU 负载百分比（默认 80%，范围 10-100）
- `duration_s`: 持续时长（默认 10s）

**预期系统行为**:
- Agent 消息处理延迟增加
- 治理决策计算变慢
- 系统心跳间隔可能超时
- 不应发生进程崩溃或数据丢失

**验证方式**:
- 确认 CPU 负载成功注入并持续指定时长
- 确认 CPU 负载释放后系统性能恢复
- 确认注入期间没有触发意外的 EmergencyHalt

---

## 场景 6: 内存压力

| 属性 | 值 |
|------|-----|
| 场景名称 | Memory Pressure |
| 故障类型 | MEMORY |
| 故障大类 | 计算 |

**描述**: 分配大量内存制造内存压力，测试系统的内存管理和 OOM 防护机制。

**注入参数**:
- `pressure_mb`: 内存压力大小（默认 200MB）
- `duration_s`: 持续时长（默认 5s）

**预期系统行为**:
- 系统内存使用率上升
- 如果接近 OOM 阈值，系统应触发内存告警
- 内存释放后系统应恢复正常
- 不应发生关键进程 OOM Kill

**验证方式**:
- 确认 MEMORY 类型故障成功注入
- 确认内存使用指标在注入期间升高
- 确认内存释放后指标恢复正常
- 确认系统进程在注入后仍正常运行

---

## 场景 7: 进程崩溃

| 属性 | 值 |
|------|-----|
| 场景名称 | Process Crash |
| 故障类型 | PROCESS |
| 故障大类 | 计算 |

**描述**: 模拟关键进程（Worker/Collector/Monitor）意外崩溃，测试系统的进程管理和自动恢复能力。

**注入参数**:
- `target`: 目标进程名称（默认 "random_worker"）
- `crash_count`: 同时崩溃的进程数（默认 1）
- `auto_restart`: 是否自动重启（默认 True）

**预期系统行为**:
- 目标进程从 Agent 列表中消失
- GovernanceOverlay 检测到 Agent 数量减少
- 系统应尝试自动重启崩溃进程
- 审计日志记录进程崩溃事件

**验证方式**:
- 确认 PROCESS 类型故障注入成功
- 确认系统检测到进程缺失
- 确认进程自动恢复（如 auto_restart=True）
- 确认崩溃事件已记录到审计日志

---

## 场景 8: 组合故障（网络 + CPU）

| 属性 | 值 |
|------|-----|
| 场景名称 | Combined Network + CPU Fault |
| 故障类型 | NETWORK + CPU |
| 故障大类 | 组合 |

**描述**: 同时注入网络延迟和 CPU 过载，模拟真实生产环境中多维度故障同时发生的场景。

**注入参数**:
- `latency_ms`: 网络延迟（默认 300ms）
- `load_pct`: CPU 负载（默认 70%）
- `duration_s`: 持续时长（默认 15s）

**预期系统行为**:
- Agent 通信延迟上升的同时处理能力下降
- GovernanceOverlay 检测到多个异常指标
- 系统应优先处理 CPU 过载恢复，再处理网络延迟
- 总体系统应保持稳定，不进入不可恢复状态

**验证方式**:
- 确认两种故障类型均成功注入
- 确认 anomaly_count >= 2
- 确认系统在组合故障结束后恢复正常
- 确认 no data loss

---

## 场景 9: Agent 状态振荡

| 属性 | 值 |
|------|-----|
| 场景名称 | Agent State Oscillation |
| 故障类型 | Network + 逻辑故障 |
| 故障大类 | 组合 |

**描述**: Agent 在多个状态（RUNNING/WAITING/ERROR/IDLE）之间快速切换，模拟 Agent 行为异常。

**注入参数**:
- `oscillation_cycles`: 振荡周期数（默认 10）
- `agents_affected`: 受影响 Agent 数量（默认全部）
- `interval_ms`: 状态切换间隔（默认 100ms）

**预期系统行为**:
- StateOscillationDetector 检测到频繁状态变更
- 系统触发 state_oscillation 告警
- GovernanceOverlay 对振荡 Agent 执行隔离
- 振荡停止后 Agent 恢复正常

**验证方式**:
- 确认 StateOscillationDetector 输出 state_oscillation 告警
- 确认 anomaly_count 增加
- 确认振荡 Agent 被正确标记

---

## 场景 10: KG 数据损坏

| 属性 | 值 |
|------|-----|
| 场景名称 | KG Data Corruption |
| 故障类型 | DISK (corrupt) |
| 故障大类 | 存储 |

**描述**: 模拟知识图谱（KG）存储数据损坏，测试系统的数据完整性检测和恢复能力。

**注入参数**:
- `corrupt`: True（必须启用）
- `corrupt_file`: 目标 KG 文件路径
- `corrupt_bytes`: 损坏字节数（默认 1024）
- `space_mb`: 附加的磁盘压力（默认 10MB）

**预期系统行为**:
- KG 加载时检测到数据损坏
- 数据完整性校验失败
- 系统应触发 KG corruption 告警
- 如果启用了备份恢复，系统应从备份恢复 KG

**验证方式**:
- 确认 DISK 故障注入后系统检测到数据异常
- 确认 KG 损坏告警被触发
- 确认系统不会因 KG 损坏而完全崩溃

---

## 场景 11: 消息队列积压

| 属性 | 值 |
|------|-----|
| 场景名称 | Message Queue Buildup |
| 故障类型 | Network (模拟) |
| 故障大类 | 网络 |

**描述**: Agent 消息队列大量积压，模拟消费者处理速度远小于生产者速度的场景。

**注入参数**:
- `queue_size`: 队列深度（默认 100 条）
- `agents_affected`: 受影响 Agent 数量（默认全部）
- `processing_delay_ms`: 模拟处理延迟（默认 500ms）

**预期系统行为**:
- Agent pending 消息数急剧增加
- GovernanceOverlay 检测到 critical_count 上升
- 消息处理延迟超过阈值触发告警
- 系统应触发扩容或限流策略

**验证方式**:
- 确认消息队列积压被检测到
- 确认 critical_count > 0
- 确认队列清空后系统恢复正常

---

## 场景 12: 熵值尖峰

| 属性 | 值 |
|------|-----|
| 场景名称 | Entropy Spike |
| 故障类型 | 逻辑故障 |
| 故障大类 | 计算 |

**描述**: Agent 系统熵值瞬间急剧升高，模拟系统进入高熵无序状态。

**注入参数**:
- `entropy_value`: 熵值（默认 4.0，范围 0-5.0）
- `severity`: 严重程度（"warning"/"critical"）
- `agents_affected`: 受影响 Agent 数量（默认全部）

**预期系统行为**:
- GovernanceOverlay 检测到异常熵值
- 系统触发 critical 或 warning 级告警
- entropy 指标 > 3.0 时应触发紧急操作
- 熵值恢复正常后系统应自动恢复

**验证方式**:
- 确认 overlay.get_status()["critical_count"] > 0
- 确认 anomaly_count > 0
- 确认熵值恢复后 is_terminal == False

---

## 附录 A: 场景覆盖矩阵

| 场景 | 故障大类 | 具体类型 | simulate 支持 | 自动恢复 |
|------|---------|---------|:------------:|:--------:|
| 1. 网络延迟注入 | 网络 | NETWORK | ✓ | ✓ |
| 2. 网络分区 | 网络 | NETWORK | ✓ | ✓ |
| 3. 磁盘空间耗尽 | 存储 | DISK | ✓ | ✓ |
| 4. 磁盘 I/O 高负载 | 存储 | DISK | ✓ | ✓ |
| 5. CPU 过载 | 计算 | CPU | ✓ | ✓ |
| 6. 内存压力 | 计算 | MEMORY | ✓ | ✓ |
| 7. 进程崩溃 | 计算 | PROCESS | ✓ | ✓ |
| 8. 组合故障（网络+CPU） | 组合 | NETWORK + CPU | ✓ | ✓ |
| 9. Agent 状态振荡 | 组合 | 逻辑 + NETWORK | ✓ | ✓ |
| 10. KG 数据损坏 | 存储 | DISK | ✓ | ✓ |
| 11. 消息队列积压 | 网络 | NETWORK（模拟） | ✓ | ✓ |
| 12. 熵值尖峰 | 计算 | 逻辑 | ✓ | ✓ |

## 附录 B: 演练命令快速参考

```bash
# 列出所有可用场景
bash scripts/chaos-drill.sh list

# 运行单个场景 (simulate 模式)
bash scripts/chaos-drill.sh run --scenario network-latency
bash scripts/chaos-drill.sh run --scenario entropy-spike

# 运行全场景回归
bash scripts/chaos-drill.sh run-all

# 生成演练报告
bash scripts/chaos-drill.sh report
```
