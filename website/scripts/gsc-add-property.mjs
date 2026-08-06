import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP, { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Step 1: Navigate to GSC welcome
  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'load'
  });
  await sleep(3000);

  // Step 2: Find RPC names from the page scripts for adding URL-prefix properties
  const rpcInfo = await page.evaluate(() => {
    // Search for RPC-related code in all scripts
    const scripts = document.querySelectorAll('script:not([src])');
    const rpcMatches = [];
    for (const s of scripts) {
      const text = s.textContent || '';
      // Look for patterns like JJETff, wXWaGb (5-6 char RPC IDs)
      const rpcs = text.match(/['"]([A-Za-z]{4,8})['"]\s*[\[:]/g);
      if (rpcs) {
        rpcMatches.push(...rpcs.map(r => r.replace(/['"\[\]:]/g, '')));
      }
    }
    // Also look for common GSC RPCs
    const unique = [...new Set(rpcMatches)];
    return unique.filter(r => r.length >= 4 && r.length <= 8).slice(0, 50);
  });
  console.log('RPCs found:', rpcInfo.join(', '));

  // Step 3: Try creating URL-prefix property via batchexecute API
  // Use the network request interception approach
  const apiCalls = [];
  page.on('request', async (req) => {
    if (req.url().includes('batchexecute')) {
      try {
        const postData = req.postData();
        if (postData) {
          apiCalls.push({
            url: req.url(),
            body: decodeURIComponent(postData).substring(0, 1000),
            time: Date.now(),
          });
        }
      } catch(e) {}
    }
  });

  // Click the URL-prefix tab using Playwright's proper locator API
  console.log('\nClicking URL prefix tab...');
  const tab = page.locator('[role="tab"]').filter({ hasText: '网址前缀' }).first();
  await tab.click({ force: true });
  await sleep(2000);

  // Check which tab is active
  const activeTab = await page.evaluate(() => {
    const tabs = document.querySelectorAll('[role="tab"]');
    for (const t of tabs) {
      const selected = t.getAttribute('aria-selected');
      if (selected === 'true') return t.textContent?.trim() || '';
    }
    return 'none selected';
  });
  console.log('Active tab:', activeTab);

  // Try filling input using native value setter + all events
  console.log('Setting URL value...');
  await page.evaluate(() => {
    const inputs = document.querySelectorAll('input[type="text"]');
    const input = inputs[inputs.length - 1]; // last visible input
    if (input) {
      // Try every possible way to set the value
      const proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      proto.call(input, 'https://maref.cc/');

      // Dispatch all events
      ['focus', 'keydown', 'input', 'keyup', 'change', 'blur'].forEach(type => {
        input.dispatchEvent(new Event(type, { bubbles: true }));
      });

      // Try React-specific event simulation
      const nativeInputValue = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
      );
      nativeInputValue.set.call(input, 'https://maref.cc/');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  await sleep(1000);

  // Try clicking continue by coordinates
  console.log('Finding continue button...');
  const continuePos = await page.evaluate(() => {
    const all = document.querySelectorAll('*');
    for (const el of all) {
      if (el.textContent?.trim() === '继续' && el.offsetParent !== null) {
        const r = el.getBoundingClientRect();
        return { x: r.x + r.width/2, y: r.y + r.height/2 };
      }
    }
    return null;
  });
  if (continuePos) {
    console.log(`Clicking continue at (${continuePos.x}, ${continuePos.y})`);
    await page.mouse.click(continuePos.x, continuePos.y);
    await sleep(8000);
  }

  // Check result
  const text = await page.evaluate(() => document.body?.innerText?.substring(0, 600) || '');
  console.log(`\nURL: ${page.url()}`);
  console.log('Text:', text.replace(/\n/g, ' | ').substring(0, 400));

  // Check API calls related to property creation
  console.log(`\nAPI calls: ${apiCalls.length}`);
  apiCalls.forEach((c, i) => {
    console.log(`\nAPI ${i}: ${c.body.substring(0, 400)}`);
  });

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
