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

  // Get all cookies
  const cookies = await page.context().cookies();
  console.log(`Total cookies: ${cookies.length}`);
  console.log('---');

  // Filter for auth-relevant cookies
  const relevant = cookies.filter(c =>
    c.name.includes('SID') || c.name.includes('SSID') || c.name.includes('APISID') ||
    c.name.includes('SAPISID') || c.name.includes('HSID') || c.name.includes('LSID') ||
    c.name.includes('oauth') || c.name.includes('token') || c.name.includes('auth') ||
    c.name.includes('__Secure') || c.name.includes('__Host')
  );
  console.log(`Auth-relevant cookies: ${relevant.length}`);
  relevant.forEach(c => console.log(`  ${c.name}: ${c.value.substring(0, 20)}... (domain: ${c.domain}, secure: ${c.secure}, httpOnly: ${c.httpOnly})`));

  // Also get the SAPISID hash for Authorization header
  // Google APIs use SAPISID hash for auth
  const sapisid = cookies.find(c => c.name === 'SAPISID');
  const ssid = cookies.find(c => c.name === 'SSID');
  const apisid = cookies.find(c => c.name === 'APISID');

  if (sapisid) {
    // SAPISID hash is used for the Authorization header
    // Format: SAPISIDHASH <timestamp>_<SHA1(timestamp + " " + SAPISID + " " + origin)>
    console.log('\nSAPISID:', sapisid.value);
    console.log('SAPISID domain:', sapisid.domain);
  }

  // Try to make a direct API call from the page context to test
  console.log('\nTrying direct API call with cookies...');
  const result = await page.evaluate(async () => {
    try {
      const resp = await fetch(
        'https://search.google.com/search-console/api/sites',
        { method: 'GET', credentials: 'include' }
      );
      return { status: resp.status, text: (await resp.text()).substring(0, 300) };
    } catch (e) {
      return { error: e.message };
    }
  });
  console.log('API call result:', JSON.stringify(result, null, 2));

  writeFileSync('/tmp/gsc-cookies.json', JSON.stringify(cookies, null, 2));
  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
