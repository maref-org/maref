# P0 告警 Runbook: [告警名称]

## 告警条件
- 指标: [PromQL 查询]
- 阈值: [触发条件]
- 优先级: P0

## 影响面
- 用户: [哪些用户受影响]
- 功能: [哪些功能受影响]

## 诊断步骤
1. 检查 [Dashboard URL]
2. 检查日志: `kubectl logs -n maref -l app=maref --tail=100`
3. 检查 [其他诊断]

## 缓解措施
1. [步骤 1]
2. [步骤 2]
3. 如果需要回滚: `bash scripts/rollback.sh --target [版本]`

## 事后复盘
- 创建事故复盘 Issue
- 通知: [#on-call Slack]
