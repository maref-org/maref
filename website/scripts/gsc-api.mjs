import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  console.log('Loading GSC...');
  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'networkidle'
  });
  await sleep(3000);
  console.log('Loaded');

  // Check gapi and try using it
  const gapiInfo = await page.evaluate(async () => {
    const info = {};
    if (typeof gapi !== 'undefined') {
      info.gapiExists = true;
      info.gapiVersion = gapi.version;
      if (gapi.client) {
        info.clientExists = true;
        const keys = Object.keys(gapi.client);
        info.clientKeys = keys;
      } else {
        info.clientExists = false;
      }
      // Check auth
      if (gapi.auth) {
        info.authExists = true;
        try {
          const token = gapi.auth.getToken();
          info.hasToken = !!token;
          info.tokenScopes = token?.scope;
        } catch (e) {
          info.tokenError = e.message;
        }
      }
    } else {
      info.gapiExists = false;
    }
    return info;
  });
  console.log('gapi info:', JSON.stringify(gapiInfo, null, 2));

  // Try using gapi to access Search Console
  if (gapiInfo.gapiExists && gapiInfo.clientExists) {
    console.log('\nTrying gapi.client.webmasters...');
    const result = await page.evaluate(async () => {
      const r = {};
      try {
        // Try loading the webmasters API
        await gapi.client.load('webmasters', 'v3');
        r.loaded = true;
        r.keys = Object.keys(gapi.client.webmasters || {});
      } catch (e) {
        r.error = e.message;
      }
      return r;
    });
    console.log('webmasters API:', JSON.stringify(result, null, 2));
  }

  // Try intercepting network to find API endpoint
  console.log('\nSetting up route interception...');
  const apiCalls = [];
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    if (url.includes('search-console') || url.includes('webmasters') || url.includes('googleapis')) {
      apiCalls.push({ url: url.substring(0, 200), method: route.request().method() });
    }
    await route.continue();
  });

  // Now try clicking the button - via coordinate tap
  const rect = await page.evaluate(() => {
    const el = document.querySelector('.U26fgb.O0WRkf.oG5Srb.C0oVfc.masrze.M9Bg4d');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height };
  });
  if (rect) {
    console.log(`Button at (${rect.x}, ${rect.y}) size ${rect.w}x${rect.h}`);
    await page.mouse.click(rect.x, rect.y);
    await sleep(3000);
    console.log(`URL after click: ${page.url()}`);
  }

  // Check intercepted API calls
  console.log('\nIntercepted API calls:');
  apiCalls.forEach(c => console.log(`  ${c.method} ${c.url}`));

  await page.unroute('**/*');
  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
