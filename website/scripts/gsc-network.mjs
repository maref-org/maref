import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Capture network requests
  const requests = [];
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    // Capture XHR/fetch calls, not static assets
    if (url.includes('search-console') || url.includes('googleapis') || url.includes('gstatic') || method !== 'GET') {
      requests.push({ url: url.substring(0, 200), method, type: route.request().resourceType() });
    }
    await route.continue();
  });

  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'load'
  });
  await sleep(5000);

  // Filter for XHR/fetch calls
  console.log('XHR/Fetch calls during load:');
  requests
    .filter(r => r.type === 'xhr' || r.type === 'fetch' || r.type === 'other' || r.method !== 'GET')
    .forEach(r => console.log(`  ${r.method} ${r.url} (${r.type})`));

  // Also check for POST/API calls
  const apiCalls = requests.filter(r => r.method !== 'GET');
  console.log(`\nNon-GET requests: ${apiCalls.length}`);
  apiCalls.forEach(r => console.log(`  ${r.method} ${r.url}`));

  await page.unroute('**/*');
  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
