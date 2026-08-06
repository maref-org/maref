# MAREF SEO & Analytics 操作清单

## ✅ 已完成（代码层面）

- [x] Cloudflare Workers + D1 自托管分析（路由: `maref.cc/api/collect`）
- [x] llms.txt + llms-zh.txt（GEO：AI 搜索爬虫友好）
- [x] robots.txt（允许 OAI/Perplexity/Claude/Google 爬虫，阻止训练爬虫）
- [x] sitemap.xml（`@astrojs/sitemap` i18n 自动生成）
- [x] BreadcrumbList JSON-LD（DocLayout 已包含）
- [x] Organization + SoftwareApplication + WebSite + Article Schema
- [x] Blog tags（6 篇文章均已加 tags + 页面标签展示）
- [x] meta keywords（BaseLayout 已加）
- [x] Open Graph + Twitter Card + hreflang + canonical

## 🔲 需要仪表板操作（手动）

### 1. Cloudflare Pages D1 绑定
Dashboard → Workers & Pages → `maref-cc` → Settings → Functions → **D1 Database Bindings**
- Variable name: `DB`
- Database: `maref-analytics`

### 2. Google Search Console
1. 打开 https://search.google.com/search-console
2. 添加 `maref.cc` 作为新属性
3. 选择 "DNS TXT record" 验证方式
4. 复制 TXT 值 → 到 Cloudflare DNS 添加记录 → 验证

### 3. 百度站长平台
1. 打开 https://ziyuan.baidu.com/
2. 添加 `maref.cc` 站点
3. 选择 DNS 验证 → 添加 TXT 记录到 Cloudflare DNS
4. 提交 sitemap: `https://maref.cc/sitemap-index.xml`
5. 在 BaseLayout.astro 中替换 `YOUR_BAIDU_VERIFICATION_CODE`

### 4. Cloudflare Web Analytics（可选增强）
Dashboard → Analytics & Logs → Web Analytics → 添加站点 → `maref.cc`
→ 获取 token → 在 BaseLayout.astro 取消注释 CF Web Analytics 代码

### 5. 启用 Workers 路由
Worker `maref-analytics` 已部署，路由 `maref.cc/api/*` 已激活。
验证: `curl -X POST https://maref.cc/api/collect -H "Content-Type: application/json" -d '{}'`

---

## 日常查询

```bash
# 总览
./scripts/analytics.sh summary

# 国家分布
./scripts/analytics.sh countries

# 来源渠道
./scripts/analytics.sh referrers

# 热门页面
./scripts/analytics.sh top-pages

# 实时最近 10 条
./scripts/analytics.sh realtime

# 每日趋势
./scripts/analytics.sh daily
```
