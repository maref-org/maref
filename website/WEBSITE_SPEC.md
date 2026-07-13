# maref.cc 网站规范

> **上位法**: [宪法第四-A条](/Volumes/1TB-M2/openclaw/CLAUDE.md) → [双仓库操作规范](/Volumes/1TB-M2/openclaw/AGENT_ARCHITECTURE.md)
> **设计素材源**: `/Volumes/1TB-M2/Athena知识库/执行项目/2026/003-open human（碳硅基共生）/018-v0.2.0-活跃/021-架构设计/MAREF递归演进框架/22-maref.cc网站/maref.cc-网站素材研究报告.md`
> **版本**: v1.0 | **生效**: 2026-06-13 | **维护者**: 所有 Code Agent

---

## 第 1 章 — 治理与项目总览

### 1.1 项目身份

| 字段 | 值 |
|------|-----|
| 域名 | https://maref.cc |
| 品牌 | MAREF (Multi-Agent Recursive Evolution Framework) |
| 定位 | Agent Governance OS — 智能体安全治理操作系统 |
| GitHub | https://github.com/maref-org/maref |
| 许可证 | Apache-2.0 |
| 版本 | v0.30.0-GA（网站版本独立于框架版本） |

### 1.2 治理归属（重要）

```
源仓库: openclaw/ (Track A — frankiehot-tech/Athena 私仓)
部署目标: Cloudflare Pages (基础设施，非 git push to public)

不可向 maref-org/maref 推送网站代码（违反宪法第四-A条）
网站代码是 Track A 资产，受双仓库安全规则保护
```

**预检清单（每次操作前）**:
```bash
pwd                                    # 必须在 /Volumes/1TB-M2/openclaw/apps/maref-cc/
ls .git/hooks/pre-push .git/hooks/pre-commit  # hook 必须存在
```

### 1.3 文件结构

```
openclaw/apps/maref-cc/
├── WEBSITE_SPEC.md          ← 本文件（Agent 操作第一参考）
├── public/                  ← 静态资源（构建时直接复制）
│   ├── llms.txt             ← LLM 爬虫入口
│   ├── robots.txt           ← 爬虫权限控制
│   ├── favicon.ico
│   └── og-image.png         ← 社交分享图 1200×630
├── src/
│   ├── content/             ← 内容（Markdown / MDX）
│   │   ├── pages/           ← 独立页面
│   │   ├── features/        ← 功能详情
│   │   ├── blog/            ← 技术博客
│   │   └── i18n/            ← 多语言翻译
│   ├── components/          ← UI 组件
│   │   ├── ui/              ← 通用 UI
│   │   ├── sections/        ← 页面区块
│   │   ├── animations/      ← 动画封装
│   │   └── geo/             ← GEO 专用组件（结构化数据注入）
│   ├── layouts/             ← 页面布局
│   ├── lib/                 ← 工具函数
│   └── styles/              ← 全局样式
├── scripts/                 ← 构建/维护脚本
│   ├── geo-audit.sh         ← GEO 审计运行器
│   ├── sync-content.sh      ← 从知识库同步内容
│   └── deploy.sh            ← Cloudflare Pages 部署
├── astro.config.ts          ← 框架配置
├── tailwind.config.ts       ← Tailwind 配置
└── package.json
```

---

## 第 2 章 — 品牌视觉系统

### 2.1 核心标识

| 字段 | 值 |
|------|-----|
| 品牌名 | MAREF（全大写） |
| 全称 | Multi-Agent Recursive Evolution Framework |
| 定位语 | Agent Governance OS |
| 副标题 | TLA+ 形式化验证 · 零信任架构 · OWASP Agentic 安全 |

**禁止**: MAREF/Maref/maref 混用、过度营销文案、承诺具体性能数字（除非可验证）

### 2.2 色彩体系

```css
/* 主色板 */
--color-bg-primary:    #0a0a0b;    /* 深色背景 */
--color-bg-secondary:  #18181b;    /* 卡片/区块背景 */
--color-bg-tertiary:   #27272a;    /* hover/强调背景 */
--color-bg-code:       #1a1b1e;    /* 代码块背景 */

--color-accent-blue:   #3b82f6;    /* 主强调色 — 科技蓝 */
--color-accent-cyan:   #06b6d4;    /* 次强调色 — 青绿 */
--color-accent-green:  #10b981;    /* 安全/信任 */
--color-accent-amber:  #f59e0b;    /* 警告 */
--color-accent-red:    #ef4444;    /* 危险/停止 */

--color-text-primary:  #fafafa;    /* 正文 */
--color-text-secondary:#a1a1aa;    /* 辅助文字 */
--color-text-muted:    #71717a;    /* 弱化文字 */
--color-text-inverse:  #18181b;    /* 浅色背景上文字 */

--color-border:        #27272a;    /* 边框 */
--color-border-hover:  #3f3f46;    /* 边框 hover */
```

**设计原则**:
- 主背景用 `#0a0a0b` 而非纯黑 `#000` — 保持层次感
- 科技蓝 `#3b82f6` 为主 CTA，青绿 `#06b6d4` 为功能卡片点缀
- 翡翠绿 `#10b981` 仅用于安全/通过/信任状态
- 红 `#ef4444` 仅用于危险/攻击/阻断场景

### 2.3 字体

```css
--font-ui:    'Inter', system-ui, sans-serif;
--font-code:  'JetBrains Mono', 'Fira Code', monospace;
--font-display: 'Inter', system-ui, sans-serif;
```

| 用途 | 字重 | 字号 | 行高 |
|------|------|------|------|
| Hero 标题 | 700 | clamp(2.5rem, 6vw, 4.5rem) | 1.1 |
| 章节标题 h2 | 600 | clamp(1.5rem, 3vw, 2.25rem) | 1.2 |
| 卡片标题 h3 | 600 | clamp(1.125rem, 1.5vw, 1.5rem) | 1.3 |
| 正文 | 400 | clamp(0.9375rem, 1vw, 1.0625rem) | 1.6 |
| 辅助文字 | 400 | 0.875rem | 1.5 |
| 代码 | 400 | 0.875rem | 1.5 |

### 2.4 Logo 使用

- Logo 文件: `/Volumes/1TB-M2/openclaw/assets/brand/maref-logo-400.png`
- 始终使用原始 Logo，不重新绘制
- 深色背景上用白色/青色 Logo
- 最小尺寸: 32px（favicon）/ 120px（导航）

---

## 第 3 章 — 设计系统

### 3.1 组件层级

```
layouts/
├── BaseLayout.astro        ← 全局 HTML、字体、SEO meta
├── LandingLayout.astro     ← 首页布局（全宽、深色）
├── DocLayout.astro         ← 文档页面布局（侧边栏）
└── BlogLayout.astro        ← 博客布局

sections/                   ← 页面区块（首页用）
├── Hero.astro
├── ProblemStatement.astro  ← 行业问题
├── ArchitectureShowcase.astro  ← 六层架构图
├── FeatureCardGrid.astro
├── DataWall.astro          ← 数据墙
├── CompetitiveTable.astro
├── CTASection.astro
└── Footer.astro

ui/                         ← 通用 UI
├── Button.astro
├── Card.astro
├── CodeBlock.astro
├── Badge.astro
├── Tabs.astro
└── ThemeToggle.astro
```

### 3.2 间距与网格

```css
/* 间距系统 (4px 步进) */
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
--space-24: 6rem;     /* 96px */

/* 内容区最大宽度 */
--content-max: 1280px;
--content-narrow: 768px;

/* 节间距 */
--section-gap: 8rem;      /* 128px 章节间距 */
--section-gap-mobile: 4rem;
```

### 3.3 暗色主题规则

- 始终使用暗色主题（亮色模式非必需）
- 不要用纯黑 `#000`，用 `#0a0a0b` 作为最深色
- 卡片用 `bg-secondary: #18181b` + 1px 边框 `#27272a`
- 阴影用青蓝色调而非灰色：`box-shadow: 0 0 20px rgba(59,130,246,0.1)`
- 大块留白，保持呼吸感

---

## 第 4 章 — 技术栈

### 4.1 获批技术栈

| 层 | 选择 | 原因 |
|---|------|------|
| 框架 | **Astro** | 内容驱动、零 JS 输出、SSG 原生、MDX 支持 |
| CSS | **Tailwind CSS v4** | 设计 token 一致性、零运行时 |
| 动画 | **Motion** (原 Framer Motion) | scroll-driven、轻量、React 集成 |
| 3D | **Three.js / R3F** | 架构图交互（按需加载） |
| 图表 | **d3.js** | 收敛曲线、状态机可视化 |
| 部署 | **Cloudflare Pages** | CDN、SSL、域名原生 |
| 分析 | Cloudflare Web Analytics | 隐私友好、免费 |

### 4.2 禁止引入

- ❌ React/Vue/Svelte 全家桶（Astro Islands 按需加载 JS）
- ❌ jQuery 等遗留库
- ❌ Google Analytics（隐私政策冲突）
- ❌ 外部字体托管（自托管 Inter + JetBrains Mono）
- ❌ 未审计的 npm 包（需确认安全后再引入）

### 4.3 构建输出

```bash
# 开发
npm run dev              # localhost:4321

# 构建
npm run build            # → dist/ 目录

# GEO 审计（构建后运行）
bash scripts/geo-audit.sh

# 部署
npm run deploy           # Cloudflare Pages
```

---

## 第 5 章 — 动画系统

### 5.1 动画原则

1. **叙事驱动** — 每个动画必须推进故事，不是装饰
2. **性能优先** — 只 animate `transform` 和 `opacity`（GPU 合成）
3. **克制** — 首页动画密度 ≤ 3 个动画区域/视口
4. **可访问** — 尊重 `prefers-reduced-motion`
5. **移动优先** — 复杂动画在移动端降级为静态

### 5.2 动画库及用法

| 库 | 用途 | 加载方式 |
|----|------|---------|
| `motion` (Motion) | scroll-driven 渐入/上移/卡片 | Astro Islands (client:visible) |
| `d3.js` + `d3-graphviz` | 状态机图、数据图表 | 按需加载 (client:idle) |
| `Three.js` / `R3F` | 3D 架构图交互 | 按需加载 (client:visible) |

### 5.3 预设动画模式

```tsx
// 模式 1: scroll-reveal — 进入视口时动画
const ScrollReveal = ({ children }) => (
  <motion.div
    initial={{ opacity: 0, y: 40 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: "-100px" }}
    transition={{ duration: 0.6, ease: "easeOut" }}
  >
    {children}
  </motion.div>
);

// 模式 2: staggered-fade — 列表依次出现
const StaggerList = ({ items }) => (
  <motion.div variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}>
    {items.map(item => (
      <motion.div variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}>
        {item}
      </motion.div>
    ))}
  </motion.div>
);

// 模式 3: counter — 数字滚动动画
const AnimatedCounter = ({ target, duration = 2000 }) => { /* useMotionValue + useTransform */ };

// 模式 4: architecture-drilldown — 分层展开
// 用于六层架构图，滚动到对应章节时高亮对应层
```

### 5.4 核心动画场景

| 场景 | 动画手法 | 触发 |
|------|---------|------|
| Gray Code FSM | 状态灯 6bit 逐位跳转 + 连线高亮 | scroll reveal |
| 8层防御 | 攻击箭头逐层穿透 + 在第5层爆炸消散 | scroll reveal |
| 四级决策树 | 操作流过 4 级节点，绿色/红色路径 | scroll reveal |
| 收敛曲线 | SVG line 从抖动到平滑绘制 | scroll reveal |
| 数据墙数字 | counter 从 0 滚到目标值 | viewport enter |
| 竞品对比 | 行依次高亮 + MAREF 列突出 | viewport enter |

### 5.5 Motion Canvas 视频制作

- 技术解释视频（社媒/文档嵌入）使用 Motion Canvas (TypeScript)
- 每条视频 = 一个独立 TS 脚本，放在 `scripts/videos/`
- 视频嵌入网站作为 `<video>` 标签（自动播放、静音、循环）

---

## 第 6 章 — GEO 要求

### 6.1 强制性 GEO 文件

| 文件 | 用途 | 验证命令 |
|------|------|---------|
| `/public/llms.txt` | LLM 爬虫索引 | `geo llms --validate` |
| `/public/robots.txt` | 允许 AI 爬虫 | `geo audit --check-robots` |
| `/public/.well-known/ai.txt` | AI 发现端点 | `geo audit --check-discovery` |

**robots.txt 关键规则**:
```txt
# 允许引用的爬虫（必须允许）
User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /

# 禁止训练的爬虫
User-agent: GPTBot
Disallow: /

User-agent: anthropic-ai
Disallow: /
```

### 6.2 Schema.org 结构化数据

所有页面必须包含 JSON-LD，类型包括：

| 页面 | Schema 类型 | 必填字段 |
|------|------------|---------|
| 首页 | `SoftwareApplication` + `Organization` | name, description, url, applicationCategory, offers |
| 功能页 | `TechArticle` | headline, description, author, datePublished |
| 博客 | `Article` | headline, datePublished, author, image |
| FAQ | `FAQPage` | mainEntity (Question/Answer) |

执行命令: `geo schema --type <type> --url <url>`

### 6.3 内容 GEO 规则

每条内容须满足 Princeton GEO 方法的前 4 项（按优先级）：

| 优先级 | 方法 | 要求 |
|--------|------|------|
| 🔴 1 | 引用来源 | 每条数据必须有外部链接或文献引用 |
| 🔴 2 | 统计数据 | 包含具体数字、百分比、日期 |
| 🟠 3 | 专家引用 | 引用研究或行业报告原文 |
| 🟠 4 | 权威语气 | 自信、专业、避免模糊表达 |

禁止关键字堆砌（已证实无效）。

### 6.4 持续监控

- 每次构建后自动运行 `geo audit --url https://maref.cc`
- 目标: GEO score ≥ 85/100
- 如得分下降，阻塞部署

---

## 第 7 章 — 国际化

### 7.1 语言支持

| 语言 | 优先级 | URL 路径 | 内容深度 |
|------|--------|---------|---------|
| 英文 | P0 | `/en/`（默认） | 完整网站 |
| 简体中文 | P0 | `/zh/` | 完整网站（含所有技术内容） |

### 7.2 翻译策略

- 不是逐字翻译，而是 **内容重新表达**
- 技术术语保持英文原型（Gray Code FSM, CircuitBreaker, Lyapunov）
- 营销文案需中英文各自撰写（参考 apple.com vs apple.com.cn 差异）
- 翻译存储在 `src/content/i18n/{locale}/` 下的 YAML 文件

### 7.3 hreflang 配置

```html
<link rel="alternate" href="https://maref.cc/en/" hreflang="en" />
<link rel="alternate" href="https://maref.cc/zh/" hreflang="zh" />
<link rel="alternate" href="https://maref.cc/" hreflang="x-default" />
```

---

## 第 8 章 — 内容管理

### 8.1 内容来源

| 内容类型 | 来源 | 同步方式 |
|---------|------|---------|
| 产品描述 | `public/maref/README.md` | 脚本同步 |
| 技术白皮书 | `public/maref/docs/MAREF-Technical-Whitepaper-zh-CN.md` | 手动选取段落 |
| 版本发布 | `public/maref/CHANGELOG.md` | 脚本同步 |
| 社媒内容 | `21-社媒内容/01-社媒内容规范-v1.0.md` | 引用叙事锚点 |
| 架构图 | `12-MAREF 系统架构/` | 手动设计为交互版本 |

### 8.2 更新流程

1. Agent 在 `src/content/pages/` 下编辑 Markdown
2. 运行 `npm run build` 验证无构建错误
3. 运行 `bash scripts/geo-audit.sh` 验证 GEO 得分
4. 提交到 openclaw 仓库（Track A）
5. 触发 Cloudflare Pages 自动部署

---

## 第 9 章 — 构建与部署

### 9.1 构建命令

```bash
npm install             # 首次/依赖变更后
npm run dev             # 本地开发 http://localhost:4321
npm run build           # 生产构建 → dist/
npm run preview         # 预览构建产物
bash scripts/geo-audit.sh  # GEO 审计
npm run deploy          # 部署到 Cloudflare Pages
```

### 9.2 Cloudflare Pages 配置

| 配置 | 值 |
|------|-----|
| 构建命令 | `npm run build` |
| 输出目录 | `dist/` |
| Node 版本 | 20+ |
| 环境变量 | 无（纯静态） |
| 域名 | maref.cc（已配 Cloudflare） |
| SSL | 自动（Full strict） |

---

## 第 10 章 — Agent 维护手册

### 10.1 每次操作前

```bash
# 1. 确认在正确目录
cd /Volumes/1TB-M2/openclaw/apps/maref-cc/
pwd

# 2. 确认仓库合规
git remote -v | grep frankiehot-tech/Athena

# 3. 确认 hook 存在
ls .git/hooks/pre-push .git/hooks/pre-commit

# 4. 读一遍本规范（WEBSITE_SPEC.md）
# 5. 读当前 STATE.yaml
cat /Volumes/1TB-M2/public/maref/STATE.yaml
```

### 10.2 禁止的操作

- ❌ 向 `maref-org/maref` 推送网站代码
- ❌ 引入未审计的依赖
- ❌ 删除 GEO 文件（llms.txt, robots.txt, schema）
- ❌ 添加非获批的分析/追踪脚本
- ❌ 覆盖品牌色系
- ❌ 在非 openclaw 路径下维护网站源文件

### 10.3 定期维护

| 频率 | 任务 | 工具 |
|------|------|------|
| 每次构建 | GEO 审计 | `geo audit --url https://maref.cc` |
| 每周 | 内容更新（与 public/maref 同步） | `scripts/sync-content.sh` |
| 每月 | 品牌一致性检查 | 人工审查 |
| 每版本发布 | 更新功能描述、数据墙 | 参照 CHANGELOG |
| 每季度 | 竞品对比表更新 | 人工研究 |
| 按需 | 博客发布 | MDX 撰写 |

### 10.4 故障恢复

- 构建失败 → 检查 `npm run build` 错误输出 → 修复内容/组件
- GEO 分下降 → `geo audit --url https://maref.cc --format json` 定位原因
- 部署失败 → 登录 Cloudflare Dashboard → 查看部署日志 → 回滚到上一版本

---

*规范版本: v1.0 | 创建: 2026-06-13 | 维护: Code Agents via openclaw governance*
