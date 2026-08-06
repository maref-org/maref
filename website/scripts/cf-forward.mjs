import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP, { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Step 1: Go to Cloudflare Email Routing page
  console.log('1. Navigating to Cloudflare Email Routing...');
  await page.goto('https://dash.cloudflare.com/?to=/:zone/email/routing', {
    timeout: 30000, waitUntil: 'load'
  });
  await sleep(5000);
  console.log(`   URL: ${page.url().substring(0, 120)}`);

  // Check state
  const state = await page.evaluate(() => {
    const t = document.body?.innerText || '';
    return {
      isLogin: t.includes('Sign in') || t.includes('Sign up') || t.includes('登录'),
      isEmailRouting: t.includes('Email') || t.includes('Routing') || t.includes('路由'),
      snippet: t.substring(0, 400),
      url: location.href,
    };
  });
  console.log('   State:', JSON.stringify(state, null, 2));

  // Step 2: If dashboard loaded, navigate to Email Routing
  if (state.isEmailRouting && !state.isLogin) {
    console.log('\n2. Already logged in! Adding athenabot@qq.com...');

    // Try navigating to email routing page for maref.cc zone
    await page.goto('https://dash.cloudflare.com/70625a7eb912b193d7f3d455f9a5916b/email/routing', {
      timeout: 30000, waitUntil: 'load'
    });
    await sleep(5000);
    console.log(`   URL: ${page.url()}`);

    const emailState = await page.evaluate(() => {
      const t = document.body?.innerText || '';
      return { snippet: t.substring(0, 800), url: location.href };
    });
    console.log('   Email State:', JSON.stringify(emailState, null, 2));
  }

  // Step 3: Try the SPF update via Cloudflare DNS page
  if (!state.isLogin) {
    console.log('\n3. Trying to add SPF record...');
    await page.goto(`https://dash.cloudflare.com/70625a7eb912b193d7f3d455f9a5916b/dns`, {
      timeout: 30000, waitUntil: 'load'
    });
    await sleep(5000);
    const dnsState = await page.evaluate(() => {
      const t = document.body?.innerText || '';
      return { snippet: t.substring(0, 800), url: location.href };
    });
    console.log('   DNS State:', JSON.stringify(dnsState, null, 2));
  }

  if (state.isLogin) {
    console.log('\n❌ Need Cloudflare login. No session available.');
  }

  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync('/tmp/cf-error.txt', e.stack || e.message);
});
