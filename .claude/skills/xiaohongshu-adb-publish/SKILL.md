---
name: xiaohongshu-adb-publish
description: >
  Publish content to 小红书 (Xiaohongshu / RED) via ADB automation.
  Covers Chinese text input (DEX clipboard injection + KEYCODE_PASTE),
  photo selection, post creation, and known blockers (no ADB-based deletion,
  React Native UI limitations). Use this when the user asks to post to 小红书
  or automate 小红书 content publishing.
version: 1.0.0
created: 2026-06-16
updated: 2026-06-27
dependencies:
  - adb (Android Debug Bridge)
  - skills/qiuzhi-narrative-style
user-invocable: true
---

# 小红书 ADB 发布自动化

> **Skill ID**: `xiaohongshu-adb-publish`
> **版本**: v1.0
> **创建日期**: 2026-06-17
> **基于**: 实测 XHS16 成功发布 + 3 次失败排障

---

## 一、架构概览

```
┌─────────────────────────────────────────────┐
│              post_xiaohongshu_adb.py          │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  │
│  │content_ │→ │adb_shell │→ │inject_clip │  │
│  │pool     │  │tap/dump  │  │+paste      │  │
│  └─────────┘  └──────────┘  └────────────┘  │
└─────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
   content_pool.py   adb shell     ClipboardFromFile2.java
   (统一内容池)      (触控/截图)   (DEX 剪贴板注入)
```

**工作流**: `content_pool 读内容 → ADB 打开 App → 选择图片 → 注入文字 → 点击发布`

---

## 二、核心技术栈

### 2.1 中文文本输入（关键突破）

小红书输入框需要中文输入。通过常规 `input text` 只能输入 ASCII，中文必须走剪贴板。

**推荐方案 A — DEX 剪贴板注入（可靠）**:
```
1. java 编译:  javac ClipboardFromFile2.java  →  classes.dex
2. 推送到设备: adb push classes.dex /data/local/tmp/
3. 执行注入:   adb shell dalvikvm -cp /data/local/tmp/classes.dex ClipboardFromFile2 /data/local/tmp/clip.txt
4. 粘贴:       adb shell input keyevent KEYCODE_PASTE
```

**方案 A 的 ClipboardFromFile2.java** — 通过 `ServiceManager.getService("clipboard")` 直接注入系统剪贴板:

```java
import java.lang.reflect.Method;
import java.io.FileInputStream;

public class ClipboardFromFile2 {
    public static void main(String[] args) throws Exception {
        if (args.length == 0) { return; }
        FileInputStream fis = new FileInputStream(args[0]);
        byte[] buf = new byte[fis.available()];
        int len = fis.read(buf);
        fis.close();
        String text = new String(buf, 0, Math.max(len, 0), "UTF-8");

        Object binder = Class.forName("android.os.ServiceManager")
            .getMethod("getService", String.class).invoke(null, "clipboard");
        Object clipboard = Class.forName("android.content.IClipboard$Stub")
            .getMethod("asInterface", Class.forName("android.os.IBinder"))
            .invoke(null, binder);
        Object data = Class.forName("android.content.ClipData")
            .getMethod("newPlainText", Class.forName("java.lang.CharSequence"), Class.forName("java.lang.CharSequence"))
            .invoke(null, (Object) null, text);

        Class<?> icClass = Class.forName("android.content.IClipboard");
        for (Method m : icClass.getMethods()) {
            if (!m.getName().equals("setPrimaryClip")) continue;
            Class<?>[] pt = m.getParameterTypes();
            Object[] p = new Object[pt.length];
            p[0] = data;
            if (pt.length > 1) p[1] = "com.android.shell";
            for (int i = 2; i < pt.length; i++) {
                if (pt[i] == int.class) p[i] = 0;
                else if (pt[i] == boolean.class) p[i] = false;
                else if (pt[i] == String.class) p[i] = "shell";
            }
            m.invoke(clipboard, p);
        }
        System.out.println("OK (" + text.length() + ")");
    }
}
```

**替代方案 B — ADB Keyboard IME + KEYCODE_PASTE**:
```
# 设置 ADB Keyboard 为默认输入法
adb shell ime set com.android.adbkeyboard/.AdbIME
# 注入剪贴板
adb shell am broadcast -a clipper.set -e text "中文内容"
# 粘贴
adb shell input keyevent KEYCODE_PASTE
# 恢复原输入法
adb shell ime set com.sohu.inputmethod.sogou/.SogouIME
```

**注意**: 方案 B 的 `clipper.set` broadcast 在某些设备可能不可用。方案 A（DEX 注入）更底层，适配性更强。

### 2.2 ADB 触控与 UI 解析

```
adb shell input tap x y          # 点击坐标
adb shell uiautomator dump ...   # 导出 UI XML
adb shell input keyevent KEYCODE_PASTE  # 粘贴
adb shell input keyevent KEYCODE_BACK   # 返回
```

**UI XML 解析注意**: 小红书大量使用 React Native 页面，其内部元素不暴露在 uiautomator XML 中。所以不能依赖 `text=` / `content-desc=` 定位，需配合**坐标定位**。

### 2.3 内容池集成

```python
from maref.promotion.content_pool import load_pool
from maref.promotion.history import add_entry

post = [p for p in load_pool("xiaohongshu") if p.id == "XHS16"][0]
TITLE = post.title
CONTENT = post.body
TAGS = post.tags
FULL_TEXT = f"{TITLE}\n\n{CONTENT}\n" + " ".join(f"#{t}" for t in TAGS)
```

内容池路径: `openclaw/data/promotion/xiaohongshu_pool.yaml`

---

## 三、标准发布流程

### 3.1 前置条件

- [ ] Android 设备已连接（`adb devices` 可见）
- [ ] 小红书 App 已登录（需要人工扫码/短信登录）
- [ ] 照片已准备好（至少 1 张在 DCIM）
- [ ] DEX clipboard jar 已编译推送

### 3.2 一键发布脚本

```bash
cd openclaw
python scripts/post_xiaohongshu_adb.py
```

### 3.3 手动步骤（如果脚本失败）

```
1. adb shell monkey -p com.xingin.xhs -c android.intent.category.LAUNCHER 1
2. 等待启动 → 点击底部 "+" 按钮（坐标约 540, 2400）
3. 选择相册 → 选择照片 → 点击"下一步"
4. 进入编辑页 → 点击正文输入框
5. 推送文字: 
   echo "正文内容" > /tmp/clip.txt && adb push /tmp/clip.txt /data/local/tmp/
   adb shell dalvikvm -cp /data/local/tmp/classes.dex ClipboardFromFile2 /data/local/tmp/clip.txt
   adb shell input keyevent KEYCODE_PASTE
6. 点击"发布"（右上角，坐标约 1000, 80）
```

### 3.4 发布后验证

```
# 截屏确认
adb exec-out screencap -p > /tmp/xhs_verify.png
# 检查 uiautomator 中是否有发布成功提示
adb shell uiautomator dump /data/local/tmp/uidump.xml
adb shell cat /data/local/tmp/uidump.xml | grep -i "发布"
```

---

## 四、已知问题与限制

### 4.1 ❌ 无法通过 ADB 删除帖子（BLOCKER）

**现象**: 点击帖子详情页的"..."按钮（右上角）→ 弹出分享面板 `moreOperateIV` → **无删除选项**

**该面板列出**: 编辑 / 置顶笔记 / 薯条推广 / 举报 / 关注话题（版本差异，不显示删除）

**尝试过的方案（均失败）**:

| 方案 | 结果 | 原因 |
|------|------|------|
| 帖子详情 → "..." → 分享面板 | ❌ 无删除 | 当前版本 share sheet 不含删除按钮 |
| 编辑页 → "设置" → WebView | ❌ 无删除 | 只有笔记原创声明/允许合拍/内容类型 |
| 创作者中心 → 笔记管理 | ❌ 无法定位 | React Native，uiautomator 读不到内容 |
| 长按缩略图 | ❌ 无菜单 | 直接打开帖子详情 |
| 浏览器网页版 | ❌ 无法登录 | 需要手机号验证码，无法自动化 |
| Content Provider 查询 | ❌ private | `com.xingin.xhs.provider` private，shell 无权限 |
| `/data/data/com.xingin.xhs/` | ❌ 无 root | 无 root 权限无法读取 |
| `adb backup` | ❌ 需要设备确认 | 交互式确认，无法无人值守 |
| `curl` 调用 API | ❌ 无认证 | 设备有 curl，但无 auth token/cookie |

**结论**: 小红书当前版本（2026年）的 ADB 自动化**不支持删除帖子**。删除操作需人工介入（App 内手动删除或登录浏览器版）。

### 4.2 ⚠️ React Native UI 不可解析

小红书创作者中心、笔记详情页等核心界面是 React Native 实现。`uiautomator dump` 在这些页面只能看到根布局（`android.widget.FrameLayout` ），内部元素全部不暴露。这意味着:
- 无法通过 text/content-desc 定位元素
- 必须依赖屏幕坐标定位（适应性差，不同屏幕需调整）
- 无法获取笔记 ID、阅读量、点赞数等元数据

### 4.3 ⚠️ 版本兼容性

坐标点击依赖 UI 布局。不同小红书版本、不同 Android 屏幕尺寸需重新校准:
- "发布"按钮坐标
- "+" 按钮坐标
- 相册选择坐标

建议每个目标设备先人工走一遍流程，记下关键坐标。

### 4.4 ⚠️ DEX 注入兼容性

`ClipboardFromFile2.java` 使用反射调用 Android 内部 API。不同 Android 版本 `IClipboard` 接口可能有差异:
- Android 10+: `setPrimaryClip(ClipData, String)` — 2 参数
- Android 12+: 增加了 `setPrimaryClip(ClipData, String, int)` — 3 参数（source）
- Android 14+: 可能增加布尔参数

代码已通过反射自适应参数数量，大多数情况可自动兼容。

---

## 五、内容格式规范

### 5.1 标题与正文

```
标题: 1 行，不超过 20 字，必须有吸引力
正文: 200-500 字，必须有空行分段，口语化
话题标签: 3-5 个 #标签 放在正文末尾
```

### 5.2 配图要求

```
格式: JPEG/PNG
数量: 1-6 张（实测 1 张可用）
尺寸: 1080x1440 最佳（竖版 3:4）
来源: comfyui_workspace/视频工作流资料/Athena 定妆照片/
```

### 5.3 内容池 YAML 格式

```yaml
posts:
  - id: XHS16
    type: knowledge
    title: "你的 AI Agent 凌晨三点在干嘛？你不知道的事多了"
    content: |
      正文内容，支持多行
    tags:
      - AI安全
      - Agent治理
```

---

## 六、故障排查指南

### 问题 1: `uiautomator dump` 返回空或超时
**可能原因**: 页面是 React Native → **解决方案**: 改用坐标定位，不要依赖 UI XML

### 问题 2: `KEYCODE_PASTE` 不生效
**可能原因**: 当前输入法不支持 ADB 粘贴 → **解决方案**: 
```
adb shell ime list -a  # 查看可用输入法
adb shell ime set com.android.adbkeyboard/.AdbIME  # 切换到 ADB Keyboard
# 或用 DEX 方案绕过输入法
```

### 问题 3: 点击坐标不对
**可能原因**: 设备分辨率不同 → **解决方案**: 
```
adb shell wm size  # 获取屏幕尺寸
# 按比例重新计算坐标
```

### 问题 4: 小红书闪退
**可能原因**: 版本过旧或资源不足 → **解决方案**: 更新到最新版，清理缓存

### 问题 5: 发布后看不到帖子
**可能原因**: 被审核拦截 / 未登录 → **解决方案**: 检查小红书审核状态，确认登录状态

---

## 七、关联文件

| 文件 | 路径 | 用途 |
|------|------|------|
| 主脚本 | `openclaw/scripts/post_xiaohongshu_adb.py` | 全自动发布 |
| 内容池 | `openclaw/data/promotion/xiaohongshu_pool.yaml` | 帖子内容定义 |
| 发布历史 | `openclaw/data/promotion/publish_history.json` | 统一记录 |
| DEX 工具 | `/tmp/ClipboardFromFile2.java` | 剪贴板注入源码 |
| 内容模块 | `openclaw/src/maref/promotion/` | 共享引擎 |
| Athena 形象 | `comfyui_workspace/视频工作流资料/Athena 定妆照片/athena-face-reference.jpg` | 封面图 |

---

## 八、限制 & 后续优化方向

### 当前不可自动化
- ❌ 删除已发帖子（需人工）
- ❌ 编辑已发帖子
- ❌ 获取笔记统计（阅读/点赞/收藏数）
- ❌ 登录（需人工扫码）

### 可优化方向
- **坐标校准工具**: 截屏 + OpenCV 模板匹配，适配不同屏幕
- **图片文字叠加**: Pillow 在封面图上叠加标题和品牌标识
- **批量发布**: 从内容池读取多个帖子顺序发布
- **审核状态监测**: 发布后定时截屏检查有无审核提示
- **Safari Web 方案**: 如果 macOS Safari 已登录，考虑用 Playwright 发布

---

## 九、版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-06-17 | 初始版本，基于 XHS16 成功发布 + 3 次失败排障经验 |
