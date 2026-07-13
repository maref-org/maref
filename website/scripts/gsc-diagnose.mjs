import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Navigate and wait
  await page.goto('https://search.google.com/search-console/welcome', { timeout: 30000, waitUntil: 'networkidle' });
  await sleep(3000);

  // Dump page structure from evaluate
  const info = await page.evaluate(() => {
    const result = {
      url: location.href,
      title: document.title,
      bodyText: document.body?.innerText?.substring(0, 2000) || '',
      inputs: [],
      buttons: [],
      roles: {},
      iframes: document.querySelectorAll('iframe').length,
    };

    // All text inputs
    document.querySelectorAll('input').forEach(inp => {
      result.inputs.push({
        type: inp.type,
        'aria-label': inp.getAttribute('aria-label'),
        placeholder: inp.placeholder,
        visible: inp.offsetParent !== null,
        value: inp.value,
        rect: inp.getBoundingClientRect().toJSON(),
      });
    });

    // All buttons
    document.querySelectorAll('button, [role="button"]').forEach(btn => {
      result.buttons.push({
        text: btn.textContent?.trim()?.substring(0, 50),
        visible: btn.offsetParent !== null,
        rect: btn.getBoundingClientRect().toJSON(),
      });
    });

    // All elements with role
    document.querySelectorAll('[role]').forEach(el => {
      const role = el.getAttribute('role');
      if (!result.roles[role]) result.roles[role] = 0;
      result.roles[role]++;
    });

    return result;
  });

  console.log('URL:', info.url);
  console.log('Title:', info.title);
  console.log('Body text (first 500):', info.bodyText.substring(0, 500));
  console.log('Iframes:', info.iframes);
  console.log('\n--- Roles ---');
  for (const [role, count] of Object.entries(info.roles)) {
    console.log(`  ${role}: ${count}`);
  }
  console.log('\n--- Inputs ---');
  info.inputs.forEach((inp, i) => {
    if (inp.visible || inp.type === 'text') {
      console.log(`  [${i}] type=${inp.type} label="${inp['aria-label']}" visible=${inp.visible} value="${inp.value}"`);
    }
  });
  console.log('\n--- Buttons ---');
  info.buttons.forEach((btn, i) => {
    if (btn.visible) console.log(`  [${i}] text="${btn.text}" visible=${btn.visible}`);
  });

  writeFileSync('/tmp/gsc-body.txt', info.bodyText);
  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
