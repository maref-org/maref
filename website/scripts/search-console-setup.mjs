// Search Console + Baidu Webmaster automation via CDP
// Connects to existing Chrome instance (port 9225)
import { chromium } from 'playwright';

const CDP_URL = 'http://127.0.0.1:9225';
const OUTPUT_FILE = '/tmp/search-console-codes.json';

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  // Connect to existing Chrome instance
  const browser = await chromium.connectOverCDP(CDP_URL);
  const defaultContext = browser.contexts()[0];
  const pages = defaultContext.pages();
  console.log(`Connected to Chrome. Existing pages: ${pages.length}`);

  const results = { google: null, baidu: null, added_dns: false };

  // === Google Search Console ===
  console.log('\n=== Google Search Console ===');
  let gscPage;
  if (pages.some(p => p.url().includes('search.google.com'))) {
    gscPage = pages.find(p => p.url().includes('search.google.com'));
    console.log('Found existing GSC tab');
  } else {
    gscPage = await defaultContext.newPage();
    await gscPage.goto('https://search.google.com/search-console', { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
  }

  const gscUrl = gscPage.url();
  console.log(`GSC URL: ${gscUrl.substring(0, 80)}`);

  if (gscUrl.includes('search.google.com')) {
    // Check if we're logged in
    const body = await gscPage.textContent('body').catch(() => '');

    if (body.includes('maref.cc') || body.includes('property')) {
      console.log('Already has properties configured');
      results.google = 'already_configured';
    } else {
      console.log('Need to log in or add property. User action required.');
      results.google = 'login_needed';
    }
  } else {
    console.log('Not on GSC - might need login');
    results.google = 'not_on_gsc';
  }

  // === Baidu Webmaster ===
  console.log('\n=== Baidu 站长平台 ===');
  let baiduPage;
  if (pages.some(p => p.url().includes('ziyuan.baidu.com'))) {
    baiduPage = pages.find(p => p.url().includes('ziyuan.baidu.com'));
    console.log('Found existing Baidu tab');
  } else {
    baiduPage = await defaultContext.newPage();
    await baiduPage.goto('https://ziyuan.baidu.com/site/', { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
  }

  const baiduUrl = baiduPage.url();
  console.log(`Baidu URL: ${baiduUrl.substring(0, 80)}`);

  if (baiduUrl.includes('ziyuan.baidu.com')) {
    const body = await baiduPage.textContent('body').catch(() => '');
    if (body.includes('maref') || body.includes('siteadd') || body.includes('添加')) {
      console.log('Baidu Webmaster accessible');
      results.baidu = 'accessible';
    } else {
      console.log('Need login');
      results.baidu = 'login_needed';
    }
  }

  // Save results
  const fs = await import('fs');
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(results, null, 2));
  console.log(`\nResults saved to ${OUTPUT_FILE}:`, JSON.stringify(results, null, 2));

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  process.exit(1);
});
