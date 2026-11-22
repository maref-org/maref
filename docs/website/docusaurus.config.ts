import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const gaTrackingId = process.env.GA_TRACKING_ID;
const algoliaAppId = process.env.ALGOLIA_APP_ID;
const algoliaApiKey = process.env.ALGOLIA_API_KEY;

const config: Config = {
  title: 'MAREF',
  tagline: 'Multi-Agent Recursive Evolution Framework — Agent Governance OS',
  favicon: 'img/favicon.ico',

  url: 'https://maref.org',
  baseUrl: '/',

  organizationName: 'maref-org',
  projectName: 'maref',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  // 2026-11-22：Docusaurus 3 默认把 .md 当 MDX 解析，正文里任何 `{...}`
  // （比如集合写法 `{1,2}` 或公式片段）都会被当成 JS 表达式 → 构建失败。
  // 实测 blog 里 5 篇因此报 "Could not parse expression with acorn"。
  // 改为 detect：不含 JSX/import 的 .md 按 CommonMark 解析，需要 MDX 的文件
  // 用 .mdx 扩展名显式声明（docs/integrations/autogen）。
  markdown: {
    format: 'detect',
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'zh-CN'],
    localeConfigs: {
      en: { label: 'English', direction: 'ltr' },
      'zh-CN': { label: '中文', direction: 'ltr' },
    },
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/maref-org/maref/edit/main/docs/website/',
          lastVersion: 'current',
          versions: {
            current: { label: 'v0.34.0-rc', path: '/' },
          },
        },
        blog: {
          showReadingTime: true,
          blogSidebarTitle: 'Recent posts',
          blogSidebarCount: 5,
          postsPerPage: 5,
          feedOptions: {
            type: 'rss',
            copyright: `Copyright © ${new Date().getFullYear()} MAREF Contributors. Apache-2.0 License.`,
          },
        },
        theme: {
          customCss: './src/css/custom.css',
        },
        gtag: gaTrackingId ? {
          trackingID: gaTrackingId,
          anonymizeIP: true,
        } : undefined,
        sitemap: {
          lastmod: 'date',
          changefreq: 'weekly',
          priority: 0.5,
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/og-image.png',
    navbar: {
      title: 'MAREF',
      logo: { src: 'img/logo.svg', alt: 'MAREF Logo' },
      items: [
        { type: 'doc', docId: 'introduction', position: 'left', label: 'Docs' },
        { type: 'doc', docId: 'api-reference', position: 'left', label: 'API Reference' },
        { type: 'doc', docId: 'architecture', position: 'left', label: 'Architecture' },
        { to: '/blog', label: 'Blog', position: 'left' },
        { to: '/about', label: 'About', position: 'right' },
        { type: 'docsVersionDropdown', position: 'right' },
        { type: 'localeDropdown', position: 'right' },
        { to: '/security', label: 'Security', position: 'right' },
        { href: 'https://github.com/maref-org/maref', label: 'GitHub', position: 'right' },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Quickstart', to: '/docs/quickstart' },
            { label: 'Architecture', to: '/docs/architecture' },
            { label: 'API Reference', to: '/docs/api-reference' },
            { label: 'Deployment', to: '/docs/deployment' },
          ],
        },
        {
          title: 'Community',
          items: [
            { label: 'GitHub', href: 'https://github.com/maref-org/maref' },
            { label: 'Issues', href: 'https://github.com/maref-org/maref/issues' },
            { label: 'Discussions', href: 'https://github.com/maref-org/maref/discussions' },
          ],
        },
        {
          title: 'More',
          items: [
            { label: 'Terms of Service', to: '/terms' },
            { label: 'Security Whitepaper', href: 'https://github.com/maref-org/maref/blob/main/docs/MAREF-Security-Whitepaper.md' },
            { label: 'Changelog', href: 'https://github.com/maref-org/maref/releases' },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} MAREF Contributors. Apache-2.0 License.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'bash', 'json', 'yaml', 'typescript'],
    },
    algolia: (algoliaAppId && algoliaApiKey) ? {
      appId: algoliaAppId,
      apiKey: algoliaApiKey,
      indexName: 'maref',
      placeholder: 'Search docs...',
    } : undefined,
  } satisfies Preset.ThemeConfig,
};

export default config;
