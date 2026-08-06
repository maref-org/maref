import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Don't wait for networkidle which can timeout
  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'load'
  });
  await sleep(5000);

  // Find API paths
  const apiPaths = await page.evaluate(() => {
    const results = new Set();
    document.querySelectorAll('script').forEach(s => {
      const text = s.textContent || '';
      const matches = text.match(/["'`]\/(?:search-console|webmasters|_\/api)[^"'`]{5,80}["'`]/g);
      if (matches) matches.forEach(m => results.add(m.replace(/["'`]/g, '')));
    });
    return Array.from(results).slice(0, 50);
  });
  console.log('API paths found:');
  apiPaths.forEach(p => console.log(`  ${p}`));

  // Also try to call the Search Console v2 API
  const apiResult = await page.evaluate(async () => {
    const results = [];

    // Try the new GSC API endpoints
    const endpoints = [
      '/_/search-console/api/sites',
      '/_/search-console/data/sites',
      '/search-console/_/api/sites',
    ];

    for (const ep of endpoints) {
      try {
        const resp = await fetch(ep, { method: 'POST', credentials: 'include' });
        if (resp.status !== 404) {
          results.push({ ep, status: resp.status, text: (await resp.text()).substring(0, 100) });
        }
      } catch (e) {
        // Cross-origin errors
      }
    }
    return results;
  });
  console.log('\nAPI responses:', JSON.stringify(apiResult, null, 2));

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
