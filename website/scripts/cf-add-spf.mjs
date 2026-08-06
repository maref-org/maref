import { chromium } from 'playwright';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Go to domains page to see which zones this account has
  console.log('1. Navigating to domains...');
  await page.goto('https://dash.cloudflare.com/?to=/:zone/dns', { timeout: 30000, waitUntil: 'domcontentloaded' });
  await sleep(5000);

  let state = await page.evaluate(() => ({
    url: location.href.substring(0, 200),
    text: (document.body?.innerText || '').substring(0, 500),
  }));
  console.log('State:', JSON.stringify(state, null, 2));

  // Look for maref.cc in the page
  const hasMaref = state.text.includes('maref');
  console.log('Has maref.cc:', hasMaref);

  // If redirected to DNS page for a zone, we're good
  if (state.url.includes('/dns')) {
    console.log('Already on DNS page!');
    
    // Find SPF record
    const spfRecord = await page.evaluate(() => {
      const rows = document.querySelectorAll('tr');
      for (const row of rows) {
        const text = row.textContent || '';
        if (text.includes('SPF') || (text.includes('v=spf1'))) {
          return text.substring(0, 300);
        }
        // Also check for TXT records with spf
        const cells = row.querySelectorAll('td');
        for (const cell of cells) {
          if (cell.textContent?.includes('v=spf1')) {
            return row.textContent?.substring(0, 300) || '';
          }
        }
      }
      return null;
    });
    console.log('SPF Record:', spfRecord);

    if (spfRecord) {
      // Try to click edit on that record
      console.log('Found SPF record, trying to edit...');
      
      // Click the record row to edit
      const editBtn = page.locator('tr:has-text("v=spf1") button, tr:has-text("v=spf1") [role="button"]').first();
      if (await editBtn.isVisible().catch(() => false)) {
        await editBtn.click();
        await sleep(2000);
        
        const editState = await page.evaluate(() => ({
          text: (document.body?.innerText || '').substring(0, 500),
        }));
        console.log('Edit state:', JSON.stringify(editState, null, 2));
      }
    }
  } else {
    console.log('Not on DNS page. Current URL:', state.url);
    
    // Try to find maref.cc zone and navigate to it
    const marefLink = page.locator('a:has-text("maref.cc")').first();
    if (await marefLink.isVisible().catch(() => false)) {
      await marefLink.click();
      await sleep(3000);
      
      // Now should be on zone page, navigate to DNS
      await page.goto(`${state.url.split('?')[0]}/dns`, { timeout: 30000, waitUntil: 'domcontentloaded' }).catch(() => {});
      await sleep(3000);
    }
  }

  // Final state
  const final = await page.evaluate(() => ({
    url: location.href.substring(0, 200),
    text: (document.body?.innerText || '').substring(0, 800),
  }));
  console.log('\nFinal state:', JSON.stringify(final, null, 2));

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
