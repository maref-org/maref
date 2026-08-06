import type { APIRoute } from "astro";

const site = "https://maref.cc";
const updated = new Date("2026-06-16").toUTCString();

const posts = [
  {
    title: "Not 'Tested.' Proved. — Why MAREF Uses TLA+ Formal Verification",
    description: "Most security tools are 'tested.' MAREF is proved — using TLA+ model checking, Lyapunov stability analysis, and mathematical convergence guarantees.",
    url: "/en/blog/tla-plus-formal-verification",
    date: "2026-06-16",
    author: "MAREF Engineering",
  },
  {
    title: "OWASP Agentic Top 10: How MAREF Covers All 10 Critical Risks",
    description: "OWASP published the Agentic Top 10 — the definitive threat model for multi-agent systems. MAREF is the first open-source framework to cover all 10 risks.",
    url: "/en/blog/owasp-agentic-top-10",
    date: "2026-06-16",
    author: "MAREF Engineering",
  },
  {
    title: "88% of Companies Already Had an AI Agent Incident — 7 Numbers That Explain the Crisis",
    description: "Gartner says 40% of enterprise apps will integrate AI agents. 88% already had an incident. 17x more spent on AI-powered security than securing AI itself. Only 6% have a mature strategy.",
    url: "/en/blog/88-percent-incidents",
    date: "2026-06-13",
    author: "MAREF Engineering",
  },
  {
    title: "GitHub Is Becoming a Giant AI Code Dump",
    description: "630M repos, half of new code is AI-written, trust dropped from 77% to 60%. CMU found 6M fake stars. AI code has 1.7x more critical bugs than human-written code.",
    url: "/en/blog/vibe-coding-crisis",
    date: "2026-06-13",
    author: "MAREF Engineering",
  },
  {
    title: "Why Agent Governance Matters in 2026",
    description: "Multi-agent systems are entering production. Without governance, every agent is an unmonitored vector for data leaks, hallucination propagation, and adversarial exploitation.",
    url: "/en/blog/why-agent-governance-matters-2026",
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
    <title>MAREF Blog — Agent Governance</title>
    <description>Thoughts on agent governance, multi-agent security, formal verification, and building trustworthy AI systems.</description>
    <link>${site}/en/blog</link>
    <language>en</language>
    <lastBuildDate>${updated}</lastBuildDate>
    <atom:link href="${site}/en/feed.xml" rel="self" type="application/rss+xml"/>
    ${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
};
