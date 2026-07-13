import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Track API calls via events
  const apiCalls = [];
  page.on('request', req => {
    if (req.url().includes('batchexecute')) {
      apiCalls.push({
        type: 'request',
        url: req.url(),
        method: req.method(),
        body: req.postData() || '',
        time: Date.now(),
      });
    }
  });

  page.on('response', async (resp) => {
    if (resp.url().includes('batchexecute')) {
      try {
        const body = await resp.text();
        apiCalls.push({
          type: 'response',
          url: resp.url(),
          status: resp.status(),
          body: body.substring(0, 3000),
          time: Date.now(),
        });
      } catch (e) {
        // Response body might not be available
      }
    }
  });

  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'load'
  });
  await sleep(3000);

  // Fill domain
  await page.locator('input[aria-label="example.com"]').last().fill('maref.cc');
  await sleep(500);

  // Click 继续
  console.log('Clicking 继续...');
  await page.evaluate(() => {
    const all = document.querySelectorAll('div, button, span, [role="button"]');
    for (const el of all) {
      if (el.textContent?.trim() === '继续' && el.offsetParent !== null) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          (el.closest('[jscontroller]') || el.closest('div.U26fgb') || el).click();
          return;
        }
      }
    }
  });

  // Wait for API responses
  await sleep(8000);

  // Analyze API calls
  const requests = apiCalls.filter(c => c.type === 'request');
  const responses = apiCalls.filter(c => c.type === 'response');

  console.log(`\nRequests: ${requests.length}, Responses: ${responses.length}`);

  requests.forEach((r, i) => {
    const qs = new URLSearchParams(r.body);
    const freqs = qs.get('f.req');
    const decoded = freqs ? decodeURIComponent(freqs) : '';
    console.log(`\nReq ${i}: ${decoded.substring(0, 300)}`);
  });

  console.log('\n--- Responses ---');
  responses.forEach((r, i) => {
    console.log(`\nRes ${i} (status ${r.status}):`);
    // Try to decode
    if (r.body.startsWith(')]}\'')) {
      // Google JSON prefix
      const json = r.body.substring(4);
      try {
        const parsed = JSON.parse(json);
        console.log(JSON.stringify(parsed, null, 2).substring(0, 1500));

        // Look for verification code or domain status
        const str = JSON.stringify(parsed);
        const patterns = [
          /google-site-verification[=:]\s*["']?([a-zA-Z0-9_-]+)/i,
          /"([a-zA-Z0-9_-]{30,80})"/,
          /verification.{0,50}/i,
        ];
        for (const p of patterns) {
          const m = str.match(p);
          if (m) {
            console.log(`\n✓ MATCH: ${m[1] || m[0]}`);
            if (m[1] && m[1].length > 15) {
              writeFileSync('/tmp/gsc-code.txt', m[1]);
            }
          }
        }
      } catch (e) {
        console.log(r.body.substring(0, 500));
      }
    } else {
      console.log(r.body.substring(0, 500));
    }
  });

  // Also check current page URL
  console.log(`\n\nFinal URL: ${page.url()}`);

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
