# Auros-Inspired Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply the Auros design system (abyssal teal, particle sphere, Matter type) to maref.cc while preserving all content and i18n.

**Architecture:** Replace CSS tokens in global.css, update font imports in BaseLayout, refactor navigation style, update component-level styles (buttons, cards, hero). All content stays unchanged — only visual layer.

**Tech Stack:** Astro v6, Tailwind CSS v4, Inter (as Matter substitute)

**Dev Server:** `http://localhost:3005/` (already running)

---

### Task 1: Foundation — global.css + BaseLayout

**Files:**
- Modify: `src/styles/global.css`
- Modify: `src/layouts/BaseLayout.astro`

**Changes:**
- Replace all color tokens with Auros abyssal-teal palette
- Add Auros typography scale
- Add Auros spacing tokens
- Add Auros surface/elevation tokens
- Update font imports (Inter 400/500/700, remove JetBrains Mono weight limit)
- Update html/body base styles
- Remove light theme block (Auros is dark-only)
- Update theme toggle script
- Update `::selection` and `::-webkit-scrollbar` colors
- Add Ice Mist border as accent option
- Add gradient CSS variables

### Task 2: Navigation — transparent overlay

**Files:**
- Modify: `src/layouts/LandingLayout.astro`
- Modify: `src/layouts/BlogLayout.astro`
- Modify: `src/layouts/DocLayout.astro`
- Modify: `src/pages/404.astro`
- Modify: `src/pages/en/faq.astro`, `src/pages/zh/faq.astro`
- Modify: `src/pages/en/about.astro`, `src/pages/zh/about.astro`
- Modify: `src/pages/en/privacy.astro`, `src/pages/zh/privacy.astro`
- Modify: `src/pages/en/blog/index.astro`, `src/pages/zh/blog/index.astro`

**Changes:**
- Remove border-bottom and backdrop-blur from nav
- Make nav fully transparent (no background)
- Change nav text color to snow-sheet #ffffff
- Style language switcher as ghost outline button (white border)
- Style nav links with uppercase Matter 12px, letter-spacing 1.44px
- Remove theme toggle entirely

### Task 3: Hero section

**Files:**
- Modify: `src/components/sections/Hero.astro`

**Changes:**
- Remove gradient glow background div
- Keep animated MAREF logo but reduce size
- Update headline to Matter 86px weight 400, letter-spacing -1.22px
- Update subhead to Matter 16px #bbc7c6
- Style primary CTA as Gradient CTA Button (teal→cyan fill, 6px radius, uppercase 12px)
- Style secondary CTA as Ghost Outline Button (multi-stop gradient border)
- Add trust bar styling update (tonal trench card)
- Hero visual: remove border/shadow, let it float on abyss

### Task 4: Section components — cards, buttons, labels

**Files:**
- Modify: `src/components/sections/ProblemStatement.astro`
- Modify: `src/components/sections/SolutionTable.astro`
- Modify: `src/components/sections/AspirationSection.astro`
- Modify: `src/components/sections/MarefLiteSection.astro`
- Modify: `src/components/sections/ArchitectureShowcase.astro`
- Modify: `src/components/sections/FeatureCardGrid.astro`
- Modify: `src/components/sections/CtaSection.astro`
- Modify: `src/components/sections/CompetitiveTable.astro`

**Changes:**
- Update card backgrounds to trench #011d1c
- Update card border-radius to 16px
- Update card padding to 40px
- Add section eyebrow labels (teal dot + uppercase 12px text)
- Update all buttons to Auros style (gradient primary, ghost outline secondary)
- Remove drop shadows from cards
- Update body text to #bbc7c6 color
- Update heading styles

### Task 5: Footer + remaining elements

**Files:**
- Modify: All footer instances in layouts and page files

**Changes:**
- Update footer background to trench #011d1c
- Update footer text to fog-veil #bbc7c6
- Remove footer border-top

### Task 6: Blog & Doc pages (content pages)

**Files:**
- Layout files already covered in Task 2
- Content styling adjustments in BlogLayout and DocLayout

**Changes:**
- Update prose/code styling to match new palette
- Update sidebar styling in DocLayout

### Task 7: Build + Verify + Deploy

**Steps:**
1. Build: `npx astro build`
2. Verify 32 pages build successfully
3. Preview: check `http://localhost:3005/` for each page type
4. Deploy: `npx wrangler pages deploy dist --project-name=maref-cc`
5. Verify prod: curl `https://maref.cc/`
