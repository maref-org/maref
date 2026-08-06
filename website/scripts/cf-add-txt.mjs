import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Try the Cloudflare Domain Connect URL
  console.log('Trying Cloudflare Domain Connect...');
  await page.goto(
    'https://dash.cloudflare.com/domainconnect/v2/domainTemplates/providers/google.com/services/domain-verification/apply?domain=maref.cc',
    { timeout: 20000, waitUntil: 'load' }
  ).catch(e => console.log(`Navigation error: ${e.message}`));
  await sleep(5000);
  
  console.log(`URL: ${page.url().substring(0, 150)}`);
  const body = await page.textContent().catch(() => '');
  console.log(`Body length: ${body.length}`);
  
  // Check if we got redirected to login or if we're on a success page
  if (body.includes('login') || body.includes('Log in') || body.includes('登录')) {
    console.log('Not logged in to Cloudflare');
  } else if (body.includes('maref') || body.includes('TXT') || body.includes('DNS') || body.includes('success')) {
    console.log('Success! Found relevant content');
  } else {
    console.log('Unknown state - checking HTML...');
    // Dump first 500 chars
    const html = await page.content();
    console.log(html.substring(0, 1000));
    writeFileSync('/tmp/cf-result.html', html);
  }
  
  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/gsc-error.txt', e.stack || e.message);
});
