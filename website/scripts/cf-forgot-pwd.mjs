import { chromium } from 'playwright';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Go to Cloudflare login page
  await page.goto('https://dash.cloudflare.com/login', { timeout: 30000, waitUntil: 'domcontentloaded' });
  await sleep(3000);

  // Click "Forgot your email or password?"
  const forgotLink = page.locator('text=Forgot your email or password').first();
  if (await forgotLink.isVisible().catch(() => false)) {
    await forgotLink.click();
    await sleep(5000);

    const state = await page.evaluate(() => ({
      url: location.href.substring(0, 200),
      text: (document.body?.innerText || '').substring(0, 1000),
    }));
    console.log('Forgot password page:', JSON.stringify(state, null, 2));
    
    // Fill in the email
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    if (await emailInput.isVisible().catch(() => false)) {
      await emailInput.fill('frankiehot@hotmail.com');
      await sleep(1000);
      
      // Click submit
      const submitBtn = page.locator('button[type="submit"], button:has-text("Send"), button:has-text("Reset")').first();
      if (await submitBtn.isVisible().catch(() => false)) {
        await submitBtn.click();
        await sleep(5000);
        
        const result = await page.evaluate(() => ({
          url: location.href.substring(0, 200),
          text: (document.body?.innerText || '').substring(0, 1000),
        }));
        console.log('After reset request:', JSON.stringify(result, null, 2));
      }
    }
  }

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
