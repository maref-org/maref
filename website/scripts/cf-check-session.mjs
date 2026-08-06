import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Navigate to Cloudflare dashboard to check session
  await page.goto('https://dash.cloudflare.com', { timeout: 20000, waitUntil: 'load' })
    .catch(e => console.log(`Nav error: ${e.message}`));
  await sleep(5000);

  console.log(`URL: ${page.url().substring(0, 120)}`);

  // Check if we're logged in (dashboard URL pattern)
  if (page.url().includes('/login')) {
    console.log('Not logged in');
  } else {
    console.log('Already logged in!');
    const body = await page.textContent();
    console.log(`Body (first 300): ${body.substring(0, 300)}`);

    // Try to add DNS record via API
    const zoneId = '02754fbda61b304c516347cdd7353feb';
    const result = await page.evaluate(async (zid) => {
      try {
        const resp = await fetch(`/api/v4/zones/${zid}/dns_records`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            type: 'TXT',
            name: 'maref.cc',
            content: 'google-site-verification=<your-verification-code>',
            ttl: 120,
          })
        });
        return { status: resp.status, body: await resp.json() };
      } catch (e) {
        return { error: e.message };
      }
    }, zoneId);
    console.log('API result:', JSON.stringify(result, null, 2));
  }

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
});
