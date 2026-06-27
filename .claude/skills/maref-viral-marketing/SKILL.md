---
name: maref-viral-marketing
description: >
  Full-stack viral marketing for MAREF open-source project: digital avatar
  content generation (Athena face anchor + Qiu Zhi narrative style), multi-platform
  adaptation (Douyin/TikTok/Xiaohongshu/LinkedIn/Bilibili/YouTube), organic + Spark Ads
  distribution, and performance analytics with feedback loop. Use when the user wants to
  launch a marketing campaign or generate content for MAREF.
version: 1.0.0
created: 2026-06-16
updated: 2026-06-27
dependencies:
  - skills/qiuzhi-narrative-style
  - skills/xiaohongshu-adb-publish
  - skills/maref-visual-content
user-invocable: true
---

# MAREF Viral Marketing Agent Skill

> **版本**: v1.0
> **用途**: 数字人内容生成 → 病毒式分发 → 效果监测 → 策略优化
> **适用项目**: MAREF 开源项目 + Athena 生态
> **源文档**: `maref_viral_marketing_agent_skill.md` @ 23-开源生态策略/
> **依赖 Skill**: `athena-face-anchor`, `qiuzhi-narrative-style`

---

## 1. 执行工作流

```
Phase 1: Strategy Init → 加载 Avatar 配置 + 秋芝风格 + 话题矩阵 + 设定目标
Phase 2: Content Factory → 话题选择 → 脚本生成 → Avatar 渲染 → 平台适配
Phase 3: Distribution → 有机发布 → 评论铺底 → 6h 监测 → Spark Ads 自动触发
Phase 4: Analytics → 实时看板 → 创意疲劳告警 → 竞品追踪
Phase 5: Feedback Loop → 归因分析 → 话题矩阵更新 → 策略写入下次记忆
```

---

## 2. 核心模块

### 2.1 数字人 Avatar 模块

调用 `athena-face-anchor` skill，参数:

```json
{
  "face_anchor": "athena_neighborhood_sister_v3",
  "outfit": "casual_cream_sweater",
  "expression": "warm_concerned | confident_reassuring | curious_engaging | thoughtful_explaining",
  "background": "soft_gradient_office",
  "lip_sync": true
}
```

### 2.2 内容生成引擎

调用 `qiuzhi-narrative-style` skill。核心结构:

**TikTok/抖音 15-30s**: Hook(0-3s) → 冲突(3-8s) → 反转(8-12s) → 方案+CTA(12-15s)
**LinkedIn 60-90s**: 数据Hook → 场景痛点 → 深度揭示 → 方案 → 专业CTA

### 2.3 话题矩阵（自动轮换）

| ID | 类型 | 标题示例 | 情绪弧 |
|----|------|---------|--------|
| T01 | 数据安全恐惧 | "让Agent自动发邮件，差点泄露公司数据" | 恐慌→释然 |
| T02 | 成本失控 | "本月API账单爆炸，因为Agent进入死循环" | 愤怒→幽默 |
| T03 | 治理盲区 | "你的Agent有'驾照'吗？没有的话出事谁负责？" | 疑问→权威 |
| T04 | 对比 | "LangChain踩油门，MAREF装刹车" | 好奇→认同 |
| T05 | 行业揭秘 | "我们审计了100个Agent，73%权限越界" | 震惊→信任 |
| T06 | 用户证言 | "用了MAREF之后，Agent再也没'越界'" | 共情→向往 |

### 2.4 平台适配

| 平台 | 时长 | 分辨率 | 发布时间 |
|------|------|--------|---------|
| TikTok | 15-30s | 9:16 | 19:00-21:00 |
| 抖音 | 15-30s | 9:16 | 12:00-13:00, 18:00-20:00 |
| 视频号 | 30-60s | 9:16/16:9 | 20:00-22:00 |
| 小红书 | 30-60s | 9:16/1:1 | 11:00-13:00, 19:00-21:00 |
| LinkedIn | 60-90s | 16:9 | 08:00-09:00, 12:00-13:00 |
| Bilibili | 90-180s | 16:9 | 18:00-22:00 |

### 2.5 Spark Ads 自动触发逻辑

**条件**: 有机互动率 >6% + 播放 >1000 + 负面评论 <15%
**初始预算**: $20/天 x 3天测试
**续投判断**: CPM $4-$8 续投 / CPM >$12 暂停 / CPA(Star) <$5 加预算

### 2.6 核心 KPI

| 层级 | 指标 | 优秀线 | 警戒线 |
|------|------|--------|--------|
| 内容 | 互动率 | >6% | <3% |
| 内容 | 完播率 | >40% | <20% |
| 转化 | GitHub Star 日增 | >20 | <5 |
| 转化 | 注册转化率 | >5% | <2% |
| 投放 | CPM | $4-8 | >$12 |
| 投放 | CPA(Star) | <$5 | >$15 |

---

## 3. 快捷命令

| 命令 | 功能 |
|------|------|
| `/viral-init` | 初始化战役，询问目标和预算 |
| `/viral-content` | 生成本周内容日历 |
| `/viral-render` | 渲染指定内容的数字人视频 |
| `/viral-publish` | 执行发布 + 铺底评论 |
| `/viral-monitor` | 拉取实时数据看板 |
| `/viral-report` | 生成日报/周报/月报 |
| `/viral-optimize` | 基于数据优化下一轮策略 |

---

## 4. 风险控制清单

- [ ] 不包含攻击性竞品对比（"XX不行"→"XX解决A，MAREF解决B"）
- [ ] 数字人符合 Athena 规范（不卡通化、不夸张、亲切优先）
- [ ] 脚本通过秋芝风格审核（不死板、不官方、有节奏）
- [ ] 评论铺底策略已准备
- [ ] Spark Ads 预算在允许范围内
- [ ] 数据追踪链接已设置
- [ ] 负面评论应急预案已就绪

---

## 5. 记忆存储规范

每轮战役结束后写入:

```json
{
  "campaign_id": "maref_viral_2026w25",
  "date_range": "2026-06-17 ~ 2026-06-23",
  "target": "github_star_growth",
  "top_performing_content": { "content_id": "...", "engagement_rate": 0.082 },
  "failed_content": [{ "content_id": "...", "failure_reason": "...", "lesson": "..." }],
  "topic_weights_update": { "T01": 1.5, "T03": 1.2 },
  "next_recommendations": ["increase_T01_frequency"]
}
```

---

## 6. 依赖 Skill 调用链

```
maref-viral-marketing
  ├── athena-face-anchor     (数字人 Avatar 渲染)
  ├── qiuzhi-narrative-style (脚本语气控制)
  └── xiaohongshu-adb-publish (小红书 ADB 发布)
```
