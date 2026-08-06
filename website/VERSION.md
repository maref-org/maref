# MAREF Website Version

## v0.3.0 (current) — Auros Redesign

**Date:** 2026-06-23
**Status:** Dev server verified, pending deploy

### Changes
- Complete visual redesign inspired by Auros design system
- New color palette: abyssal teal (#012624) canvas, trench (#011d1c) cards, reef (#003734) elevated
- Typography: Matter (Inter substitute) with extreme size/tracking scale
- Transparent fixed navigation bar with uppercase tracked-out links
- Gradient CTA buttons (teal→cyan fill, multi-stop ghost outline)
- Cards: 16px radius, tonal depth instead of shadows
- Section eyebrow labels (teal dot + uppercase 10px text)
- Removed light theme toggle (dark-only Auros aesthetic)
- Removed analytics beacon to non-existent endpoint
- Spacing: 1200px max-width, 68px section gap, 40px card padding

### Known Issues
- 3 ZH pages don't contain "MAREF" string (zh/faq, zh/blog/88-percent-incidents, zh/blog/vibe-coding-crisis)
- Some ZH pages slow on cold start (Cloudflare)
- Navbar code still duplicated across 11 files (needs shared component refactor)

---

## v0.2.0 — Bugfix & i18n

**Date:** 2026-06-23

### Changes
- Fixed trailingSlash: 'always' compliance (all internal links + /)
- Restored navbar on homepage (LandingLayout was missing it)
- Fixed zh/faq.astro stray HTML tags
- Fixed 404.astro locale detection (URL-based, not navigator.language)
- Fixed ProblemStatement.astro image i18n (English pages use -en.svg)
- Fixed OWASP blog invalid CSS class
- Added "About" link to all navigation bars
- Added clsx and tailwind-merge to package.json
- Fixed all breadcrumb trailing slashes

---

## v0.1.0 — Initial Release

**Date:** 2026-06-16

### Features
- 32 static pages (EN + ZH)
- Blog engine with 5 articles per locale
- Feature pages (Governance, Defense, Evolution, Cryptography)
- FAQ, About, Privacy pages
- Interactive D3 animations (GrayCode FSM, Convergence Chart, Governance Showcase)
- i18n with astro i18n
- TLA+ formal verification content
- SEO (hreflang, JSON-LD, sitemap, RSS)
