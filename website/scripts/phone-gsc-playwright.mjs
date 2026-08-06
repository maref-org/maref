import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  console.log('Connecting...');
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Navigate to GSC
  console.log('Navigating to GSC...');
  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'networkidle'
  });
  await sleep(2000);
  console.log(`URL: ${page.url()}`);

  // Method 1: Try to call GSC internal API directly
  console.log('\n=== Method 1: Direct API call ===');
  const apiResult = await page.evaluate(async () => {
    try {
      // GSC uses internal APIs at /search-console/api/
      const resp = await fetch('https://search.google.com/search-console/api/domain/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: 'maref.cc', verificationMethod: 'DNS_TXT' })
      });
      return { status: resp.status, body: await resp.text().catch(() => '') };
    } catch(e) {
      return { error: e.message };
    }
  });
  console.log('API result:', JSON.stringify(apiResult).substring(0, 300));

  // Method 2: Click the tab/radio properly
  console.log('\n=== Method 2: Tab click ===');
  await page.evaluate(() => {
    // Find and click the 网域 tab in the tab bar
    const tabs = document.querySelectorAll('[role="tab"]');
    for (const tab of tabs) {
      if (tab.textContent.includes('网域')) {
        // Dispatch proper click events
        tab.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
        tab.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        tab.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        return true;
      }
    }
    return false;
  });
  await sleep(2000);

  // Try filling domain
  await page.evaluate(() => {
    const inputs = document.querySelectorAll('input[type="text"]');
    for (const inp of inputs) {
      if (inp.getAttribute('aria-label') === 'example.com' && inp.offsetParent !== null) {
        // Focus
        inp.focus();
        inp.dispatchEvent(new Event('focus', { bubbles: true }));
        // Set value
        const proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        proto.set.call(inp, 'maref.cc');
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    return false;
  });
  await sleep(1000);

  // Click 继续
  await page.evaluate(() => {
    const spans = document.querySelectorAll('span');
    for (const span of spans) {
      if (span.textContent.trim() === '继续' && span.offsetParent !== null) {
        span.click();
        return true;
      }
    }
    return false;
  });
  await sleep(5000);

  console.log(`URL after interaction: ${page.url()}`);

  // Method 3: Try different URL patterns
  console.log('\n=== Method 3: Direct URL navigation ===');
  const urls = [
    'https://search.google.com/search-console/verify?resource_id=sc_domain%3Amaref.cc',
    'https://search.google.com/search-console/domain_verification?domain=maref.cc',
    'https://search.google.com/search-console/setup/domain?domain=maref.cc',
    'https://search.google.com/search-console/new-domain',
  ];

  for (const url of urls) {
    console.log(`\nTrying: ${url}`);
    const resp = await page.goto(url, { timeout: 10000, waitUntil: 'domcontentloaded' }).catch(e => e.message);
    await sleep(2000);
    console.log(`  Status: ${resp?.status ? await resp.status() : 'error'}`);
    console.log(`  Final URL: ${page.url()}`);

    const body = await page.textContent().catch(() => '');
    for (const kw of ['TXT', 'DNS', '验证', '记录值', 'google-site', 'maref']) {
      if (body.includes(kw)) {
        console.log(`  Found "${kw}":`, body.substring(Math.max(0, body.indexOf(kw)-30), body.indexOf(kw)+150).substring(0, 200));
      }
    }

    // If we find the verification page, save the code
    const patterns = [
      /google-site-verification[=:]\s*["']?([a-zA-Z0-9_-]{20,60})/i,
      /content=["']([a-zA-Z0-9_-]{20,60})["'][^>]*google-site-verification/i,
      /TXT[^\n]{0,200}?([a-zA-Z0-9_-]{30,80})/i,
    ];
    for (const p of patterns) {
      const m = body.match(p);
      if (m) {
        console.log('\n✓✓✓ GSC CODE:', m[1] || m[0]);
        writeFileSync('/tmp/gsc-code.txt', m[1] || m[0]);
      }
    }
  }

  await page.screenshot({ path: '/tmp/gsc-final.png', fullPage: true });
  writeFileSync('/tmp/gsc-final.html', await page.content());

  await browser.close();
  console.log('\nDone');
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
