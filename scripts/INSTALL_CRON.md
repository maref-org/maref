# MAREF 定期内存监控 - 安装说明

## 自动安装方式（推荐）

打开终端并执行以下命令：

```bash
# 1. 复制配置文件到 launchd 目录
cp $MAREF_EXP_ROOT/scripts/com.maref.memory-monitor.plist ~/Library/LaunchAgents/

# 2. 加载配置
launchctl load ~/Library/LaunchAgents/com.maref.memory-monitor.plist

# 3. 验证是否加载成功
launchctl list | grep maref

# 4. 查看日志（可选）
tail -f $MAREF_EXP_ROOT/scripts/memory_monitor_cron.log
```

## 配置说明

- **监控频率**：每小时执行一次（3600秒）
- **自动清理**：内存使用率 ≥ 90% 时自动执行紧急清理
- **日志位置**：`$MAREF_EXP_ROOT/scripts/memory_monitor_cron.log`

## 卸载方式

```bash
# 1. 卸载配置
launchctl unload ~/Library/LaunchAgents/com.maref.memory-monitor.plist

# 2. 删除配置文件
rm ~/Library/LaunchAgents/com.maref.memory-monitor.plist
```

## 手动测试

在加载前，可以先手动测试脚本：

```bash
bash $MAREF_EXP_ROOT/scripts/cron_memory_monitor.sh
cat $MAREF_EXP_ROOT/scripts/memory_monitor_cron.log
```
