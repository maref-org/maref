// Baidu verification v13: clean approach - use existing tab, fill correctly
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9225';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];

  // Open a fresh page
  const page = await ctx.newPage();
  await page.goto('https://ziyuan.baidu.com/site/siteadd#/', { waitUntil: 'networkidle', timeout: 20000 });
  await sleep(3000);

  console.log('=== Step 1: Fill domain ===');
  // Clear and fill domain carefully - make sure it's exact
  const domainInput = page.locator('input.add-site-input');
  await domainInput.click();
  await sleep(300);
  await domainInput.fill('');
  await sleep(200);
  await domainInput.fill('maref.cc');
  await sleep(500);
  const filledVal = await domainInput.inputValue();
  console.log('Domain filled:', JSON.stringify(filledVal));

  console.log('\n=== Step 2: Select protocol ===');
  // Click protocol selector via the select-btn span
  const selectBtn = page.locator('.select-btn');
  await selectBtn.click();
  await sleep(800);

  // Click https:// option
  await page.evaluate(() => {
    const items = document.querySelectorAll('#protocolSelect .item');
    for (const it of items) {
      if (it.textContent === 'https://') {
        it.click();
        return true;
      }
    }
  });
  await sleep(500);

  const protoVal = await page.evaluate(() => {
    return document.querySelector('#protocolSelect input')?.value;
  });
  console.log('Protocol selected:', JSON.stringify(protoVal));

  console.log('\n=== Step 3: Click 下一步 ===');
  // Listen for navigation
  const navPromise = page.waitForURL('**/site/**', { timeout: 15000 }).catch(() => null);

  await page.evaluate(() => {
    document.getElementById('site-add')?.click();
  });

  // Wait for navigation or new page state
  await sleep(3000);

  const body = await page.textContent('body').catch(() => '');
  const clean = body.replace(/\s+/g, ' ');

  console.log('URL:', page.url().substring(0, 150));

  // Check CAPTCHA
  if (clean.includes('拖动') || clean.includes('滑块')) {
    console.log('\nCAPTCHA showing. Bring browser to front and solve it...');
    await page.bringToFront();
    // Wait up to 2 minutes for user to solve CAPTCHA
    for (let i = 0; i < 120; i++) {
      await sleep(1000);
      const cb = await page.textContent('body').catch(() => '');
      if (!cb.includes('拖动') && !cb.includes('滑块')) {
        console.log(`CAPTCHA solved after ${i+1}s`);
        break;
      }
    }
  }

  await sleep(2000);

  // Show current state
  const body2 = await page.textContent('body').catch(() => '');
  const clean2 = body2.replace(/\s+/g, ' ');
  console.log('\nFinal URL:', page.url().substring(0, 150));

  // Check if we're on sitespherepage (step 2 - categories)
  if (page.url().includes('sitespherepage') || clean2.includes('站点领域')) {
    console.log('\n=== Step 2: Select site categories ===');
    await page.bringToFront();
    console.log('Categories showing. Please select categories in your browser and click 下一步.');
    console.log('Waiting for you to proceed...');

    // Wait for navigation to verification step
    for (let i = 0; i < 120; i++) {
      await sleep(1000);
      const cu = page.url();
      const cb = await page.textContent('body').catch(() => '');
      if (!cu.includes('sitespherepage') && cu.includes('verify')) {
        console.log(`Navigated to verification after ${i+1}s`);
        break;
      }
      if (cb.includes('添加以下') || cb.includes('TXT') || (cb.includes('验证') && !cb.includes('站点领域'))) {
        console.log(`Verification content found after ${i+1}s`);
        break;
      }
      if (i % 15 === 14) console.log(`  Still waiting... (${i+1}s)`);
    }
    await sleep(2000);
  }

  // Extract TXT code
  const body3 = await page.textContent('body').catch(() => '');
  const clean3 = body3.replace(/\s+/g, ' ');
  console.log('\n=== Looking for TXT code ===');

  const patterns = [
    /验证[码值][：:]\s*([^\s<)"']{10,50})/,
    /TXT记录[值]*[：:]\s*([^\s<)"']{10,50})/,
    /记录值[：:]\s*([^\s<)"']{10,50})/,
    /([a-z0-9]{20,50})\.verification\.[a-z]+/,
    /baidu[-_][a-z0-9]{20,50}/i,
    /添加(?:如下|以下).{0,30}([^\s<)"']{10,50})/,
    /DNS[^:]*:[：]\s*([^\s<)"']{10,50})/i,
    /([a-z0-9_-]{20,60})\s*[（(]TXT[)）]/i,
  ];

  let txtCode = null;
  for (const pat of patterns) {
    const m = clean3.match(pat);
    if (m) {
      txtCode = m[1] || m[0];
      console.log('✓✓✓ TXT CODE:', txtCode);
      writeFileSync('/tmp/baidu-txt-code.txt', txtCode);
      break;
    }
  }

  if (!txtCode) {
    // Dump relevant sections
    ['验证', 'TXT', 'DNS', '记录值', '添加以下', '第三步'].forEach(kw => {
      const idx = clean3.indexOf(kw);
      if (idx >= 0) console.log(`\n"${kw}":`, clean3.substring(Math.max(0, idx-20), idx+300));
    });

    // Save for debugging
    await page.screenshot({ path: '/tmp/baidu-verify-final.png', fullPage: true });
    const html = await page.content();
    writeFileSync('/tmp/baidu-verify-final.html', html);
    console.log('\nScreenshot + HTML saved for debugging');
  }

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/baidu-v13-error.txt', e.stack || e.message);
});
