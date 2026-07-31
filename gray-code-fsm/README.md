# gray-code-fsm

MAREF 的 Gray Code 状态机形式化验证仓库（独立于主仓库发布）。

10 态治理 FSM（4-bit Gray code）与 24 态 Agent FSM（5-bit Gray code）的
TLA+ 规约 + 可执行模型 + Python 自包含验证器。单一事实源为
`maref-org/maref` 仓库 `src/formal/`，本目录为可独立复现的发布版副本。

## 文件清单

| 文件 | 说明 |
|------|------|
| `MarefLite.tla` | 10 态治理 FSM 静态定义（GrayCode / EntropyLevel） |
| `MarefLiteModel.tla` | 10 态可执行模型（多 Agent 推进 + 治理覆盖层 + 时序性质） |
| `MarefAgent24.tla` | 24 态 Agent FSM 静态定义（GrayCode5 / CanTransition5 / INV-001..007） |
| `MarefJoint34.tla` | 34 态联合 FSM 可执行模型（SJ-001..007 跨层约束编码进 Next） |
| `MarefLiteMC.cfg` / `MarefJoint34MC.cfg` | TLC 模型配置 |
| `validator.py` | 自包含 Python 验证器（Python 3.9+，无 maref 依赖） |
| `verify.sh` | 一键验证入口（TLC × 2 + Python validator） |

## 快速开始

```bash
./verify.sh
```

验收标准：**两个 TLC 模型均在 5 分钟内完成并输出
`No error has been found`**（本机实测 < 1s；10 态 576 distinct states，
34 态 192 distinct states）。

### 依赖

- Java 运行时：`verify.sh` 自动定位（brew openjdk 优先，其次 `$JAVA`）
- `tla2tools.jar`（TLC 2.19）：自动查找 `./tla2tools.jar` 或 `../lib/tla2tools.jar`，
  找不到时自动从 GitHub releases 下载（v1.19.1）

### 手动运行 TLC

```bash
java -XX:+UseParallelGC -cp /path/to/tla2tools.jar \
  tlc2.TLC -config MarefLiteMC.cfg MarefLiteModel
java -XX:+UseParallelGC -cp /path/to/tla2tools.jar \
  tlc2.TLC -config MarefJoint34MC.cfg MarefJoint34
```

### 手动运行 Python 验证器

```bash
python3 validator.py   # 11 项检查，exit 0 全部通过
```

## 验证分工

| 性质 | 工具 |
|------|------|
| 10 态不变量（单比特、熵 profile、吸收态、可达性） | TLC + validator.py |
| 24 态生命周期表不变量（吸收态、无孤儿、状态数） | TLC + validator.py |
| 34 态跨层不变量 JointInvariant（SJ-001/002/003/005） | TLC |
| SJ-004/SJ-006 吸收性时序性质（全路径） | TLC（`HaltGovAbsorbing` / `TerminalsAbsorbAgent`） |
| SJ-001/SJ-003 可满足性（存在路径到 (9,22)/(5,8)） | validator.py（BFS） |

> 说明：TLA+ 的 liveness 公式 `<>P` 是对**所有**行为全称量化。本模型的
> GovMove/AgentMove 为非确定选择，存在绕过目标状态的行为，因此
> `ActReachable`/`HaltReachable` 不能作为 TLC PROPERTIES 通过；存在性
> 可达性由 `validator.py` 的 BFS 检查（与 TLA+ 使用同一转移关系）。

## 与主仓库同步

`maref-org/maref` 仓库 `src/formal/` 是单一事实源。修改任一方的规约后，
需同步另一方（TLA+ 规约 + `.cfg` + `validator.py`）。

## CI

`.github/workflows/verify.yml` 在每次 push / PR 时运行本仓库全部验证。
Docker 复现可参考主仓库 `src/formal/Dockerfile.tlc`（alpine + openjdk17-jre）。
