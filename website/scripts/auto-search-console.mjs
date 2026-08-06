// Automate Google Search Console + Baidu Webmaster verification via CDP
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9225';
const OUT = '/tmp/search-console-results.json';

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const results = { google_txt: null, baidu_txt: null, error: null };

  // === 1. Google Search Console ===
  console.log('=== Google Search Console ===');
  const gPage = await ctx.newPage();
  await gPage.goto('https://search.google.com/search-console', { waitUntil: 'networkidle', timeout: 20000 }).catch(e => {
    console.log('GSC navigation:', e.message.substring(0, 60));
  });
  await sleep(3000);

  let gUrl = gPage.url();
  console.log(`URL: ${gUrl.substring(0, 100)}`);

  // Check if we need to add property
  const gBody = await gPage.textContent('body').catch(() => '');
  if (gBody.includes('添加') || gBody.includes('Add property') || gBody.includes('输入')) {
    console.log('Login required - trying to fill credentials...');
    // Try to find Google login form
    const emailInput = await gPage.$('input[type="email"], input[name="identifier"]').catch(() => null);
    if (emailInput) {
      console.log('Found email input - login required, cannot automate fully');
      results.google_txt = 'LOGIN_REQUIRED';
    } else {
      results.google_txt = 'CHECK_MANUALLY';
    }
  } else if (gBody.includes('maref.cc') || gBody.includes('属性') || gBody.includes('property')) {
    console.log('Already has site configured!');
    results.google_txt = 'ALREADY_CONFIGURED';
  } else if (gUrl.includes('myaccount') || gUrl.includes('signin') || gUrl.includes('accounts')) {
    console.log('Redirected to login');
    // Try to see if we can interact with the login page
    results.google_txt = 'LOGIN_REQUIRED';
  } else {
    // Try to look for add property button
    const addBtn = await gPage.$('a:has-text("Add property"), button:has-text("添加"), [role="button"]:has-text("添加")').catch(() => null);
    if (addBtn) {
      console.log('Found add property button - clicking...');
      await addBtn.click().catch(() => {});
      await sleep(2000);

      // Look for domain input and DNS tab
      const domainInput = await gPage.$('input[type="url"], input[placeholder*="domain"], input[placeholder*="域名"]').catch(() => null);
      if (domainInput) {
        await domainInput.fill('maref.cc');
        await sleep(500);
        // Look for continue button
        const continueBtn = await gPage.$('button:has-text("Continue"), button:has-text("继续")').catch(() => null);
        if (continueBtn) await continueBtn.click().catch(() => {});
        await sleep(2000);

        // Look for DNS TXT value
        const txtValue = await gPage.textContent('body').catch(() => '');
        console.log(`After add property: ${txtValue.substring(0, 200)}`);
        results.google_txt = txtValue;
      }
    }
  }

  console.log(`Google result: ${results.google_txt ? results.google_txt.substring(0, 80) : 'null'}`);

  // === 2. Baidu Webmaster ===
  console.log('\n=== Baidu 站长平台 ===');
  const bPage = await ctx.newPage();
  await bPage.goto('https://ziyuan.baidu.com/site/', { waitUntil: 'networkidle', timeout: 20000 }).catch(e => {
    console.log('Baidu navigation:', e.message.substring(0, 60));
  });
  await sleep(3000);

  const bUrl = bPage.url();
  console.log(`URL: ${bUrl.substring(0, 100)}`);
  const bBody = await bPage.textContent('body').catch(() => '');

  if (bBody.includes('maref.cc') || bBody.includes('maref')) {
    console.log('Already has site!');
    results.baidu_txt = 'ALREADY_CONFIGURED';
  } else if (bBody.includes('登录') || bBody.includes('login') || bUrl.includes('passport')) {
    console.log('Login required');
    results.baidu_txt = 'LOGIN_REQUIRED';
  } else {
    console.log(`Baidu page content (first 200): ${bBody.substring(0, 200)}`);
    results.baidu_txt = 'NEEDS_LOGIN';
  }

  // Save results
  writeFileSync(OUT, JSON.stringify(results, null, 2));
  console.log(`\nDone. Results: ${JSON.stringify(results, null, 2)}`);

  await browser.close();
}

main().catch(e => {
  console.error('Fatal:', e.message);
  writeFileSync(OUT, JSON.stringify({ error: e.message }, null, 2));
  process.exit(1);
});
