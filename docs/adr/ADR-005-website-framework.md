# ADR-005: 文档网站框架 — Docusaurus + 双语 + 版本化

**状态**: 已接受
**日期**: 2026-05-14
**决策者**: MAREF 架构组

## 背景

MAREF 需要一个官方文档网站，需满足以下需求：

1. **双语支持**：英文（默认）+ 简体中文
2. **版本化文档**：每个发布版本对应一套文档
3. **代码示例**：大量 Python/TypeScript 代码块需语法高亮
4. **API 参考**：自动从代码生成或手动维护 API 文档
5. **轻量部署**：静态站点，可部署到 GitHub Pages
6. **搜索**：全局搜索能力（Algolia 集成）

## 决策

**采用 Docusaurus 2.x/3.x 作为文档网站框架，使用 `@docusaurus/preset-classic`，支持双语 (en/zh-CN) 和版本化文档。**

### 框架选择矩阵

| 框架 | 版本化 | 双语 | 代码高亮 | 搜索 | 生态 | 选择 |
|------|--------|------|----------|------|------|------|
| Docusaurus | ✅ 原生 | ✅ i18n | ✅ Prism | ✅ Algolia | ✅ Meta | **✅** |
| VuePress | ⚠️ 插件 | ✅ i18n | ✅ Prism | ✅ Algolia | ⚠️ Vue | |
| MkDocs | ⚠️ 插件 | ⚠️ 插件 | ⚠️ 插件 | ✅ 内置 | ⚠️ Python | |
| Nextra | ⚠️ 实验性 | ✅ i18n | ✅ | ⚠️ 有限 | ⚠️ Vercel | |
| ReadTheDocs | ✅ 原生 | ⚠️ 有限 | ⚠️ 有限 | ✅ 内置 | ⚠️ Sphinx | |

### 配置结构

```
docs/website/
├── docusaurus.config.ts    # 主配置
├── sidebars.ts              # 侧边栏
├── docs/                    # 英文文档源
│   ├── introduction.md
│   ├── quickstart.md
│   ├── architecture.md
│   ├── api-reference.md
│   ├── deployment.md
│   ├── integrations/        # 集成指南
│   └── cookbook/            # 场景指南
├── i18n/
│   └── zh-CN/
│       ├── docusaurus-plugin-content-docs/
│       │   └── current/     # 中文文档
│       └── code.json        # UI 文本翻译
├── versioned_docs/          # 版本化文档
├── versioned_sidebars/      # 版本化侧边栏
├── src/
│   ├── components/          # 自定义组件
│   ├── pages/               # 自定义页面
│   └── css/                 # 自定义样式
└── static/                  # 静态资源
```

### 配置要点

| 配置 | 值 | 说明 |
|------|----|------|
| url | https://maref.org | 生产域名 |
| defaultLocale | en | 默认英文 |
| locales | en, zh-CN | 双语言 |
| onBrokenLinks | throw | 严格模式 |
| Prism 主题 | github / dracula | 亮暗切换 |
| Algolia 搜索 | 配置 placeholder | 需配置 App ID |

### 版本策略

| 版本 | 标签 | 说明 |
|------|------|------|
| current | v0.33.0-rc | 最新开发版 |
| version-0.33 | v0.33 | 上一个稳定版 |

## 后果

- **正面**：Docusaurus 原生版本化和 i18n 减少定制开发
- **正面**：Prism 语法高亮覆盖 Python/TS/JSON/YAML
- **正面**：静态站点可部署到 GitHub Pages / Cloudflare Pages
- **正面**：Algolia DocSearch 提供全文搜索
- **负面**：文档需手动维护，无法从代码注释自动生成
- **负面**：双语维护需同步更新两个语言版本
- **负面**：Docusaurus 插件生态不如 Gatsby/Jekyll 成熟
- **缓解**：CI 检查文档路径完整性，双语同步在 Review 阶段检查

## 实施检查项

- [x] Docusaurus 项目初始化
- [x] 主页 (index.tsx)
- [x] 导航栏 + 页脚
- [x] 英文文档核心内容
- [x] 中文 i18n 框架
- [x] 版本化文档结构
- [x] Algolia 搜索占位
- [x] GitHub Pages 部署配置
- [ ] 文档 CI/CD 工作流
- [ ] 完整中文翻译
- [ ] 自定义 404 页面

## 替代方案

- **VuePress** — 被否决，团队熟悉 React 而非 Vue
- **MkDocs + Material** — 被否决，版本化和双语支持不如 Docusaurus
- **自建文档系统** — 被否决，维护成本高，不必要
