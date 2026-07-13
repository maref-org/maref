import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  const apiCalls = [];
  page.on('response', async (resp) => {
    if (resp.url().includes('batchexecute')) {
      try { apiCalls.push(await resp.text()); } catch(e) {}
    }
  });

  // Step 1: Try to access the URL-prefix property directly
  console.log('Trying URL-prefix property...');
  await page.goto('https://search.google.com/search-console?resource_id=https://maref.cc/', {
    timeout: 30000, waitUntil: 'load'
  });
  await sleep(5000);
  console.log(`URL: ${page.url()}`);

  let state = await page.evaluate(() => {
    const t = document.body?.innerText || '';
    return {
      isDashboard: t.includes('总点击量') || t.includes('效果') || t.includes('Performance') || t.includes(' clicks'),
      isNotVerified: t.includes('not-verified') || t.includes('未验证') || t.includes('验证您的所有权'),
      isWelcome: t.includes('欢迎使用') || t.includes('Welcome'),
      isAddProperty: t.includes('add') || t.includes('添加') || t.includes('没有找到'),
      snippet: t.substring(0, 600),
    };
  });
  console.log('State:', JSON.stringify(state, null, 2));

  // Step 2: If property doesn't exist, try adding it via the API
  if (state.isWelcome || state.isAddProperty) {
    console.log('\nProperty not found. Trying to add URL-prefix property via API...');

    // Navigate to the add property page
    await page.goto('https://search.google.com/search-console/welcome', {
      timeout: 30000, waitUntil: 'load'
    });
    await sleep(3000);

    // Collect the current _asar & RPC tokens
    const pageInfo = await page.evaluate(() => ({
      url: location.href,
      hasForm: document.body?.innerText?.includes('继续') || false,
      rpcs: Array.from(document.querySelectorAll('script')).slice(0, 5).map(s => (s.textContent || '').substring(0, 100)).filter(x => x),
    }));
    console.log('Page info:', JSON.stringify(pageInfo, null, 2));

    // Try the API approach for creating URL-prefix property
    // First get the SAPISID hash for authorization
    const cookieAuth = await page.evaluate(async () => {
      // Try using the GSC internal RPC to add a URL-prefix property
      const results = [];

      // RPC format: [rpc_name, payload, null, null]
      // Try "wXWaGb" - this might be the RPC for adding sites
      const rpcName = 'wXWaGb';
      const payload = [["https://maref.cc/", null, null, null, null, [0, 0, 0, 1, 0], null, null, null, null, null, null, null, 1, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null], 1];

      const body = new URLSearchParams();
      body.set('f.req', JSON.stringify([[rpcName, JSON.stringify(payload), null, null]]));

      try {
        const resp = await fetch('https://search.google.com/_/SearchConsoleUi/data/batchexecute', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
          },
          body: body.toString(),
        });
        const text = await resp.text();
        results.push({ rpc: rpcName, status: resp.status, body: text.substring(0, 500) });
      } catch (e) {
        results.push({ rpc: rpcName, error: e.message });
      }

      // Try different batchexecute URL
      const altUrl = 'https://search.google.com/search-console/_/batchexecute';
      const body2 = new URLSearchParams();
      body2.set('f.req', JSON.stringify([[rpcName, JSON.stringify(payload), null, null]]));
      body2.set('at', 'APoJ2wDp4gkJyAptKDn7jg3cMqE-yYMjiw:224793641');

      try {
        const resp = await fetch(altUrl, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
          body: body2.toString(),
        });
        results.push({ rpc: rpcName, url: altUrl, status: resp.status, body: (await resp.text()).substring(0, 500) });
      } catch (e) {
        results.push({ rpc: rpcName, url: altUrl, error: e.message });
      }

      return results;
    });
    console.log('API results:', JSON.stringify(cookieAuth, null, 2));
  }

  // Step 3: If property exists but not verified, try re-verification
  if (state.isNotVerified) {
    console.log('\nProperty exists but not verified. GSC will check automatically.');
    console.log('Meta tag is deployed on maref.cc - waiting for Google to crawl and verify.');
  }

  // Step 4: If we got a dashboard, SUCCESS!
  if (state.isDashboard) {
    console.log('\n*** SUCCESS! Property is verified and accessible! ***');
  }

  console.log(`\nAPI calls captured: ${apiCalls.length}`);
  apiCalls.forEach((body, i) => {
    if (body.startsWith(")]}'\n")) body = body.substring(5);
    console.log(`\nAPI ${i}: ${body.substring(0, 300)}`);
  });

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
