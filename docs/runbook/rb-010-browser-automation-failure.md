# RB-010: 桌面浏览器自动化失败

## 告警信息

- **告警名**: `MarefBrowserAutomationFailure`
- **严重级别**: P1
- **触发条件**: BrowserController 方法返回非预期结果或抛出异常

## 影响范围

- 需要浏览器交互的 Agent 任务（自动化操作、页面抓取）无法执行
- 依赖页面状态的决策流程中断
- 回退成本：人工操作产生额外 MCP 调用延迟

## 诊断步骤

1. 检查 Playwright 是否正确安装
   ```bash
   python -c "import playwright; print(playwright.__version__)"
   playwright install --list
   ```

2. 检查页面对象状态
   ```bash
   # 确认 page 实例未释放
   curl -s http://localhost:8080/api/v1/browser/status | jq .
   ```

3. 检查目标域名是否在白名单中
   ```bash
   cat config/browser-whitelist.yaml
   ```

4. 检查浏览器进程资源占用
   ```bash
   ps aux | grep -i "chromium\|firefox\|playwright" | grep -v grep
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| Playwright 未安装 | 执行 `pip install playwright && playwright install chromium` | 2-5 分钟 |
| 页面对象为 None | 重新初始化浏览器上下文：`maref browser init` | 1 分钟 |
| 域名不在白名单 | 手动添加至 browser-whitelist.yaml 并重新加载配置 | 2 分钟 |
| 浏览器进程崩溃 | 重启浏览器：`maref browser restart` | 1-2 分钟 |
| 持续失败 | 回退至手动导航模式，人工执行后通过 MCP 返回结果 | 即时 |

## 验证

```bash
curl -s http://localhost:8080/api/v1/browser/status | jq .healthy
```

## 升级路径

- 自动化失败导致关键任务阻塞 > 15 分钟：通知桌面自动化团队
- Playwright 版本兼容性问题：锁定已知稳定版本
- 频繁崩溃：检查内存泄漏或升级浏览器版本
