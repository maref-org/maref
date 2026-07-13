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

  // Fill domain
  console.log('Filling domain...');
  await page.locator('input[aria-label="example.com"]').last().fill('maref.cc');
  await sleep(500);

  // Use evaluate to dispatch a complete mouse event sequence
  console.log('Submitting via JS...');
  const submitResult = await page.evaluate(async () => {
    // Find the visible button
    function findContinueBtn() {
      const all = document.querySelectorAll('div, button, span, [role="button"]');
      for (const el of all) {
        if (el.textContent?.trim() === '继续' && el.offsetParent !== null) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            return el;
          }
        }
      }
      return null;
    }

    const btn = findContinueBtn();
    if (!btn) return 'no button found';

    console.log('Button tag:', btn.tagName);
    console.log('Button class:', btn.className?.substring(0, 80));

    // Try clicking various parent levels
    let target = btn;
    // Go up to find the Material Design button wrapper (has jscontroller)
    let parent = btn;
    while (parent && parent.tagName !== 'BODY') {
      if (parent.getAttribute('jscontroller') || parent.tagName === 'BUTTON' ||
          (parent.className?.includes('U26fgb'))) {
        target = parent;
        break;
      }
      parent = parent.parentElement;
    }

    // Sequence of events that Google Material Design expects
    const rect = target.getBoundingClientRect();
    const x = rect.x + rect.width / 2;
    const y = rect.y + rect.height / 2;

    const events = [
      ['pointermove', { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerType: 'mouse' }],
      ['pointerdown', { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerType: 'mouse', button: 0 }],
      ['mousedown', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }],
      ['focus', { bubbles: false, cancelable: false }],
      ['focusin', { bubbles: true, cancelable: false }],
      ['pointerup', { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerType: 'mouse', button: 0 }],
      ['mouseup', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }],
      ['click', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }],
    ];

    for (const [name, opts] of events) {
      target.dispatchEvent(new PointerEvent(name, { ...opts, composed: true }));
    }

    return `dispatched events on ${target.tagName}.${(target.className||'').substring(0,30)} at (${Math.round(x)},${Math.round(y)})`;
  });
  console.log(`Submit: ${submitResult}`);

  await sleep(5000);
  console.log(`URL: ${page.url()}`);

  if (!page.url().includes('welcome')) {
    // We navigated! Check for verification code
    const html = await page.content();
    for (const kw of ['TXT', 'DNS', '验证', '记录', 'google-site', 'maref', '复制', '添加以下']) {
      const idx = html.indexOf(kw);
      if (idx >= 0) console.log(`\n"${kw}": ${html.substring(Math.max(0, idx-20), idx+200)}`);
    }
  } else {
    // Try using gapi to submit
    console.log('\nTrying gapi API...');
    const apiResult = await page.evaluate(async () => {
      // Try the Google API available on the page
      const results = [];

      // Method: Try fetch to the GSC API with the auth cookie
      try {
        const resp = await fetch('/search-console/api/domain/add/v1', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ domain: 'maref.cc', method: 'dns' })
        });
        results.push(`API: ${resp.status}`);
      } catch (e) {
        results.push(`API error: ${e.message}`);
      }

      // Method: Look for Google API JS
      if (typeof gapi !== 'undefined') {
        results.push('gapi available');
      } else {
        results.push('gapi not available');
      }

      if (typeof goog !== 'undefined') {
        results.push('goog available');
      }

      return results.join(', ');
    });
    console.log(`API: ${apiResult}`);
  }

  await browser.close();
  console.log('\nDone');
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
