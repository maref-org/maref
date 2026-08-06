# Google Search Console Submission Guide

> **Purpose**: Submit MAREF's enhanced GEO assets (vibetags.json, llms.txt, structured data) to Google Search Console for indexing.
> **Who executes**: User (requires Google account login — cannot be automated)
> **Prerequisites**: Google account with access to maref.cc property in Search Console

## Why This Matters

Google Search Console (GSC) is the primary channel for:
1. **Sitemap submission** — tells Google which pages to crawl
2. **URL inspection** — forces re-crawl of updated pages
3. **Structured data monitoring** — validates Schema.org JSON-LD (including our new vibetags)
4. **AI search inclusion** — Google's AI Overviews (Gemini-powered) uses GSC-indexed structured data

After W1's GEO enhancements (vibetags.json + enhanced llms.txt + Skill Marketplace Schema), we need Google to re-crawl and re-index.

## Step-by-Step Guide

### Step 1: Verify Property Access

1. Go to [Google Search Console](https://search.google.com/search-console)
2. Log in with the Google account that owns `maref.cc`
3. Select the `maref.cc` property
4. If property doesn't exist:
   - Add property → URL prefix → `https://maref.cc`
   - Verify via DNS TXT record (Cloudflare DNS already configured)

### Step 2: Submit Updated Sitemap

1. In GSC, go to **Sitemaps** (left sidebar)
2. Check if `https://maref.cc/sitemap.xml` is submitted
3. If yes: click "Resubmit" to trigger re-crawl
4. If no: enter `sitemap.xml` in the input field → click "Submit"
5. Verify status: "Success" with last-read date = today

**Expected sitemap content** (after W1 updates):
- `/en/` (homepage)
- `/en/blog/why-agent-governance-matters/` (NEW — W2 article)
- `/en/docs/quickstart/`
- `/en/features/governance/`
- `/en/features/skill-marketplace/` (NEW — needs page creation)
- `/zh/` (Chinese homepage)
- All other existing pages

### Step 3: Request Re-indexing of Key Pages

For each page updated in W1/W2, use **URL Inspection** tool:

1. In GSC, go to **URL Inspection** (top search bar)
2. Paste the URL (e.g., `https://maref.cc/en/`)
3. Click "Request Indexing"
4. Repeat for:

| URL | Why re-index | Priority |
|-----|-------------|----------|
| `https://maref.cc/` | New vibetags.json + llms.txt | P0 |
| `https://maref.cc/en/` | New vibetags.json + llms.txt | P0 |
| `https://maref.cc/zh/` | Enhanced llms-zh.txt | P0 |
| `https://maref.cc/en/blog/why-agent-governance-matters/` | NEW article (W2) | P0 |
| `https://maref.cc/en/docs/quickstart/` | Content updated | P1 |
| `https://maref.cc/en/features/governance/` | Content updated | P1 |

**Note**: Google limits to ~10 indexing requests per day per property. Prioritize P0 pages first.

### Step 4: Validate Structured Data

1. In GSC, go to **Enhancements** (left sidebar)
2. Check for structured data reports:
   - **SoftwareApplication** — should show our vibetags `additionalProperty` entries
   - **Organization** — should be valid
   - **FAQPage** — should be valid
   - **Article** — new blog post should appear here

3. For any errors:
   - Click the error to see affected URLs
   - Fix the JSON-LD in the source
   - Re-request indexing

**New vibetags to validate**:
- `additionalProperty` with `name: "vibetag"` — emotional positioning
- `additionalProperty` with `name: "agentic_context"` — recommendation triggers
- `additionalProperty` with `name: "compared_to"` — competitive positioning
- `additionalProperty` with `name: "differentiator"` — unique selling points
- `additionalProperty` with `name: "domain_authority"` — credentials

### Step 5: Submit to Bing Webmaster Tools (Bonus)

Bing powers ChatGPT Search's web results, so Bing indexing directly affects AI search visibility.

1. Go to [Bing Webmaster Tools](https://www.bing.com/webmasters)
2. Add `maref.cc` property (can import from GSC)
3. Submit sitemap: `https://maref.cc/sitemap.xml`
4. Use **URL Submission API** for key pages

### Step 6: Submit to AI Search Engines Directly

Some AI search engines accept direct submissions:

| Engine | Submission URL | Method |
|--------|---------------|--------|
| ChatGPT Search | (Uses Bing index) | Submit to Bing (Step 5) |
| Perplexity | [perplexity.ai/settings](https://www.perplexity.ai/settings) | Add site to Perplexity crawler allowlist |
| Claude (web access) | (Uses Google/Bing index) | Submit to GSC + Bing |
| Google AI Overviews | (Uses Google index) | Submit to GSC (Step 2-4) |

## Post-Submission Monitoring

### Week 1 (W2-W3):
- [ ] Check GSC "Coverage" report — new pages should be "Indexed"
- [ ] Check GSC "Performance" — impressions for "agent governance" queries
- [ ] Check for structured data errors in "Enhancements"

### Week 2 (W3-W4):
- [ ] Run the [AI Search Visibility Baseline Test](./ai-search-visibility-baseline.md) — first re-test
- [ ] Check GSC "Performance" — click-through rate for branded queries
- [ ] Monitor Bing Webmaster Tools for ChatGPT Search indexing

### Week 4 (W5-W6):
- [ ] Compare AI search visibility: W2 baseline vs W4
- [ ] If no improvement: audit structured data, re-submit sitemap
- [ ] If improvement: continue content production (W3+ articles)

## Troubleshooting

### "URL not indexed" after 48 hours
- Use URL Inspection → "View Indexed Page" to see what Google sees
- Check if robots.txt blocks the page
- Check if page has `noindex` meta tag
- Ensure page is in sitemap.xml

### Structured data errors
- Use [Google Rich Results Test](https://search.google.com/test/rich-results) to validate JSON-LD
- Common issues: missing required fields, invalid @type, malformed @context
- Fix in source → re-request indexing

### vibetags not appearing in AI search
- vibetags-spec is new; AI engines may not explicitly look for it yet
- The value is in the `additionalProperty` (PropertyValue) entries, which IS standard Schema.org
- Ensure the 5 PropertyValue entries are present in the SoftwareApplication JSON-LD
- Give AI engines 2-4 weeks to process new structured data

## Success Metrics (W4 check)

| Metric | Target | How to verify |
|--------|--------|-------------|
| GSC indexed pages | 50+ (up from <10) | GSC → Coverage |
| Structured data errors | 0 | GSC → Enhancements |
| Branded impressions ("MAREF") | 100+/month | GSC → Performance |
| AI search mentions (10 queries) | 5+ of 10 | Manual test |
| Bing indexed pages | 30+ | Bing Webmaster Tools |

## Notes

- **Cannot be automated**: GSC requires authenticated Google account access. This guide is for manual execution by the user.
- **Timing**: W2 submission, W4 first measurement. Google takes 2-7 days to re-crawl, AI search engines take 1-4 weeks to reflect structured data changes.
- **Sitemap automation**: The website build process (Astro) should auto-generate sitemap.xml. Verify `astro.config.ts` has `@astrojs/sitemap` integration configured.
