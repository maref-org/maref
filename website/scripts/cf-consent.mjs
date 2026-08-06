import { chromium } from 'playwright';

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 30000 });
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  console.log('1. Navigating to Cloudflare login...');
  await page.goto('https://dash.cloudflare.com/login', { timeout: 30000, waitUntil: 'domcontentloaded' });
  await sleep(3000);

  // Click GitHub SSO button
  console.log('2. Looking for GitHub SSO button...');

  // Use Playwright's built-in text locator
  try {
    const githubBtn = page.getByText('GitHub', { exact: true });
    if (await githubBtn.isVisible().catch(() => false)) {
      await githubBtn.click();
      console.log('   Clicked GitHub with Playwright locator');
    } else {
      // Fallback: try the button containing "GitHub"
      const githubBtn2 = page.locator('button', { hasText: 'GitHub' });
      if (await githubBtn2.isVisible().catch(() => false)) {
        await githubBtn2.click();
        console.log('   Clicked GitHub button with hasText');
      } else {
        // Last resort: scroll to find GitHub and click by position
        const pos = await page.evaluate(() => {
          const all = document.querySelectorAll('button, a, [role="button"]');
          for (const el of all) {
            const t = el.textContent?.trim() || '';
            if (t.includes('GitHub') && el.offsetParent !== null) {
              const r = el.getBoundingClientRect();
              if (r.width > 0) return { x: r.x + r.width/2, y: r.y + r.height/2, text: t.substring(0, 30) };
            }
          }
          return null;
        });
        if (pos) {
          console.log(`   Clicking at (${Math.round(pos.x)}, ${Math.round(pos.y)}) for "${pos.text}"`);
          await page.mouse.click(pos.x, pos.y);
        } else {
          console.log('   ❌ GitHub button not found');
        }
      }
    }
  } catch (e) {
    console.log('   Error:', e.message);
  }
  await sleep(5000);

  // Check where we are now
  let state = await page.evaluate(() => ({
    url: location.href.substring(0, 150),
    text: (document.body?.innerText || '').substring(0, 500),
  }));
  console.log('   After click:', JSON.stringify(state, null, 2));

  // If redirected to GitHub login, check if already logged in
  if (state.url.includes('github.com')) {
    console.log('\n3. GitHub login page. Checking if already authenticated...');
    await sleep(5000);

    state = await page.evaluate(() => ({
      url: location.href.substring(0, 150),
      text: (document.body?.innerText || '').substring(0, 500),
    }));
    console.log('   GitHub state:', JSON.stringify(state, null, 2));

    // If there's an "Authorize" button, click it (user is already logged into GitHub)
    const authResult = await page.evaluate(() => {
      const all = document.querySelectorAll('button, input[type="submit"], [role="button"]');
      for (const el of all) {
        const t = el.textContent?.trim() || el.getAttribute('value') || '';
        if ((t.includes('Authorize') || t.includes('授权') || t.includes('Allow')) && el.offsetParent !== null) {
          el.click();
          return 'clicked authorize';
        }
      }
      return 'no authorize button';
    });
    console.log('   Auth result:', authResult);
    await sleep(5000);

    state = await page.evaluate(() => ({
      url: location.href.substring(0, 150),
      text: (document.body?.innerText || '').substring(0, 500),
    }));
    console.log('   After authorize:', JSON.stringify(state, null, 2));
  }

  // If we're now on Cloudflare dashboard, add forwarding
  if (state.url.includes('dash.cloudflare.com') && !state.url.includes('login')) {
    console.log('\n✅ Logged into Cloudflare! Adding forwarding...');

    // Navigate to email routing
    await page.goto('https://dash.cloudflare.com/70625a7eb912b193d7f3d455f9a5916b/email/routing', {
      timeout: 30000, waitUntil: 'domcontentloaded'
    });
    await sleep(5000);

    // Add athenabot@qq.com as destination
    console.log('\n4. Adding athenabot@qq.com as destination...');
    const addDest = await page.evaluate(async () => {
      try {
        const resp = await fetch('/api/v4/accounts/31bbd9c9649372287cd546db34bf894c/email/routing/addresses', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: 'athenabot@qq.com' }),
        });
        return { status: resp.status, body: await resp.text() };
      } catch (e) { return { error: e.message }; }
    });
    console.log('   Add destination:', JSON.stringify(addDest, null, 2));
  }

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
