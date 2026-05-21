# MAREF Git GC 优化 - 安装说明

## 问题诊断

当前 Git 仓库状态：
- **松散对象**: 80,287 个
- **占用空间**: 1.84 GiB
- **pack 文件**: 13 个
- **问题**: 大量松散对象导致基于 BasedPyright 的索引工具持续扫描 .git 目录

## 立即执行（推荐首次运行）

```bash
cd /Volumes/1TB-M2/maref-experiments
bash scripts/git_gc_optimize.sh
```

这将：
1. 清理 7 天前的 reflog
2. 执行激进的 GC 打包
3. 优化对象存储
4. 显示优化前后的对比

## 定期自动执行

### 方式 1：添加到 launchd（与内存监控一起）

编辑内存监控的 plist 文件，或创建独立的 Git GC 任务：

```xml
<!-- 创建 ~/Library/LaunchAgents/com.maref.git-gc.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.maref.git-gc</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Volumes/1TB-M2/maref-experiments/scripts/git_gc_optimize.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Volumes/1TB-M2/maref-experiments</string>
    <key>StandardOutPath</key>
    <string>/Volumes/1TB-M2/maref-experiments/scripts/git_gc.log</string>
    <key>StandardErrorPath</key>
    <string>/Volumes/1TB-M2/maref-experiments/scripts/git_gc.log</string>
    <!-- 每周执行一次（604800秒） -->
    <key>StartInterval</key>
    <integer>604800</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

安装命令：
```bash
cp scripts/com.maref.git-gc.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.maref.git-gc.plist
```

### 方式 2：手动定期执行

添加到你的 crontab（如果已授权）：
```bash
0 3 * * 0 bash /Volumes/1TB-M2/maref-experiments/scripts/git_gc_optimize.sh
```

## 预防性配置

在 `.gitconfig` 中添加自动 GC 配置：

```bash
git config --global gc.auto 256
git config --global gc.autopacklimit 4
git config --global gc.pruneexpire 7.days.ago
```

这会让 Git 在松散对象超过 256 个时自动执行轻量级 GC。

## 预期效果

执行 GC 后预期：
- 松散对象从 80,000+ 降至 < 1000
- .git 目录从 1.84 GiB 降至 < 500 MiB
- BasedPyright 索引速度提升（因为排除了 .git 目录）
- 磁盘 I/O 压力显著降低

## 注意事项

⚠️ **首次执行可能耗时较长**（5-15 分钟），建议在空闲时执行
⚠️ **执行期间不要进行 Git 操作**
⚠️ **如果仓库有未提交的更改，先提交或 stash**
