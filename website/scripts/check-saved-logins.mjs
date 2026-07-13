import { chromium } from 'playwright';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  // Navigate to Cloudflare login
  await page.goto('https://dash.cloudflare.com/login', { timeout: 30000, waitUntil: 'load' });
  await sleep(3000);

  // Check if there's an email field with autofill
  const state = await page.evaluate(() => {
    const inputs = document.querySelectorAll('input');
    const fields = [];
    inputs.forEach(inp => {
      fields.push({
        id: inp.id,
        name: inp.name,
        type: inp.type,
        value: inp.value,
        placeholder: inp.placeholder,
        autoComplete: inp.autocomplete,
        className: inp.className,
      });
    });
    return { url: location.href, fields };
  });
  console.log('Login page fields:', JSON.stringify(state, null, 2));

  // Try clicking the email field to trigger autofill
  const emailField = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first();
  if (await emailField.isVisible().catch(() => false)) {
    await emailField.click();
    await sleep(1000);
    // Type email to trigger password autofill
    await emailField.fill('frankiehot@hotmail.com');
    await sleep(2000);
  }

  const afterFill = await page.evaluate(() => {
    const pwds = document.querySelectorAll('input[type="password"]');
    const emails = document.querySelectorAll('input[type="email"]');
    return {
      emailVals: [...emails].map(e => e.value),
      pwdVals: [...pwds].map(p => p.value ? '****' : '(empty)'),
      pwdAutoComplete: [...pwds].map(p => p.autocomplete),
    };
  });
  console.log('After fill:', JSON.stringify(afterFill, null, 2));

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
