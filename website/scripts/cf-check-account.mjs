import { chromium } from 'playwright';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Go to account home
  await page.goto('https://dash.cloudflare.com/', { timeout: 30000, waitUntil: 'domcontentloaded' });
  await sleep(5000);

  const state = await page.evaluate(() => ({
    url: location.href.substring(0, 200),
    text: (document.body?.innerText || '').substring(0, 2000),
  }));
  console.log('Home state:', JSON.stringify(state, null, 2));

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
