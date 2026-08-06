import type { APIRoute } from "astro";

const site = "https://maref.cc";
const updated = new Date("2026-06-16").toUTCString();

const posts = [
  {
    title: "不是「测过」，是「证过」——为什么 MAREF 用 TLA+ 形式化验证",
    description: "大多数安全工具是「测过」的。MAREF 是「证过」的——使用 TLA+ 模型检验、Lyapunov 稳定性分析和数学收敛性保证。",
    url: "/zh/blog/tla-plus-formal-verification",
    date: "2026-06-16",
    author: "MAREF Engineering",
  },
  {
    title: "OWASP Agentic Top 10：MAREF 如何覆盖全部 10 项关键风险",
    description: "OWASP 发布了 Agentic Top 10——多智能体系统的权威威胁模型。MAREF 是首个覆盖全部 10 项风险的开源框架。",
    url: "/zh/blog/owasp-agentic-top-10",
    date: "2026-06-16",
    author: "MAREF Engineering",
  },
  {
    title: "88% 的公司已经翻车了——关于 AI Agent 安全的 7 个数字真相",
    description: "Gartner 说 40% 的企业应用将有 AI Agent，但 88% 已经出过事。花在'用 AI 做安全'上的钱是'保护 AI 本身'的 17 倍。仅 6% 的企业有成熟策略。",
    url: "/zh/blog/88-percent-incidents",
    date: "2026-06-13",
    author: "MAREF Engineering",
  },
  {
    title: "GitHub 正在变成一个巨型 AI 代码垃圾场",
    description: "6.3 亿仓库，一半新代码是 AI 写的，信任度从 77% 跌到 60%。CMU 挖出 600 万假 star，AI 代码严重问题是人工的 1.7 倍。",
    url: "/zh/blog/vibe-coding-crisis",
    date: "2026-06-13",
    author: "MAREF Engineering",
  },
  {
    title: "为什么智能体治理在 2026 年至关重要",
    description: "多智能体系统正在进入生产环境。没有治理，每个智能体都是数据泄露、幻觉传播和对抗性利用的未监控向量。",
    url: "/zh/blog/why-agent-governance-matters-2026",
    date: "2026-06-13",
    author: "MAREF Engineering",
  },
];

export const GET: APIRoute = async () => {
  const items = posts
    .map(
      (p) => `
    <item>
      <title><![CDATA[${p.title}]]></title>
      <description><![CDATA[${p.description}]]></description>
      <link>${site}${p.url}</link>
      <guid isPermaLink="true">${site}${p.url}</guid>
      <pubDate>${new Date(p.date).toUTCString()}</pubDate>
      <author>${p.author}</author>
    </item>`
    )
    .join("");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>MAREF 博客 — 智能体治理</title>
    <description>关于智能体治理、多智能体安全、形式化验证和构建可信 AI 系统的思考。</description>
    <link>${site}/zh/blog</link>
    <language>zh</language>
    <lastBuildDate>${updated}</lastBuildDate>
    <atom:link href="${site}/zh/feed.xml" rel="self" type="application/rss+xml"/>
    ${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
};
