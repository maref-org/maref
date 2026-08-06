import { chromium } from 'playwright';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Step 1: Check current account and try to access maref.cc DNS directly
  console.log('1. Trying to navigate to maref.cc DNS directly...');
  
  // Try the known zone ID for maref.cc
  await page.goto('https://dash.cloudflare.com/70625a7eb912b193d7f3d455f9a5916b/dns', { 
    timeout: 30000, waitUntil: 'domcontentloaded' 
  });
  await sleep(5000);

  let state = await page.evaluate(() => ({
    url: location.href.substring(0, 200),
    text: (document.body?.innerText || '').substring(0, 1000),
  }));
  console.log('State:', JSON.stringify(state, null, 2));

  // If it shows 404 or "not found", try listing zones
  if (state.text.includes('not found') || state.text.includes('404') || state.text.includes('no access')) {
    console.log('\n2. Zone not accessible in this account. Listing available zones...');
    await page.goto('https://dash.cloudflare.com/', { timeout: 30000, waitUntil: 'domcontentloaded' });
    await sleep(5000);
    
    state = await page.evaluate(() => ({
      url: location.href.substring(0, 200),
      text: (document.body?.innerText || '').substring(0, 2000),
    }));
    console.log('Home state:', JSON.stringify(state, null, 2));
  } else if (state.url.includes('/dns')) {
    // We're on the DNS page! Find SPF record
    console.log('\n3. On DNS page! Looking for SPF record...');
    
    // Wait for records to load
    await sleep(5000);
    
    const dnsState = await page.evaluate(() => ({
      url: location.href.substring(0, 200),
      text: (document.body?.innerText || '').substring(0, 3000),
    }));
    console.log('DNS page:', JSON.stringify(dnsState, null, 2));

    // Look for SPF/TXT records
    const recordList = await page.evaluate(() => {
      const rows = document.querySelectorAll('[data-testid="dns-record-row"], .dns-record-row, tr');
      const records = [];
      rows.forEach(row => {
        const text = row.textContent?.trim() || '';
        if (text) records.push(text.substring(0, 200));
      });
      return records.slice(0, 30);
    });
    console.log('Rows:', JSON.stringify(recordList, null, 2));
  }

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
