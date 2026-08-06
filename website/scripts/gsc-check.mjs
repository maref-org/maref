// Quick check: navigate to Google Search Console & Baidu via CDP
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9225';
const OUT = '/tmp/gsc-result.json';

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0] || await browser.newContext();
  const result = {};

  // === Google ===
  console.log('=== Google Search Console ===');
  const gp = await ctx.newPage();
  await gp.goto('https://search.google.com/search-console', { timeout: 15000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 4000));
  console.log('URL:', gp.url().substring(0, 120));
  const gtxt = await gp.textContent('body').catch(() => '');
  console.log('Body preview:', gtxt.substring(0, 300));

  if (gtxt.includes('Add property') || gtxt.includes('添加')) {
    // Try to fill domain 'maref.cc'
    const inputs = await gp.locator('input').all();
    for (const inp of inputs) {
      const placeholder = await inp.getAttribute('placeholder').catch(() => '');
      if (placeholder.includes('domain') || placeholder.includes('域名') || placeholder.includes('example')) {
        await inp.fill('maref.cc');
        console.log('Filled domain input');
        await new Promise(r => setTimeout(r, 1000));
        break;
      }
    }
    // Look for Continue/Add button
    const btns = await gp.locator('button, a[role="button"], [role="menuitem"]').all();
    for (const btn of btns) {
      const text = await btn.textContent().catch(() => '');
      if (text.includes('Continue') || text.includes('继续') || text.includes('添加')) {
        await btn.click().catch(() => {});
        console.log('Clicked continue/add');
        await new Promise(r => setTimeout(r, 3000));
        break;
      }
    }
    // Check result
    const body2 = await gp.textContent('body').catch(() => '');
    console.log('After submit:', body2.substring(0, 400));
    result.google = body2.substring(0, 500);
  } else {
    result.google = gtxt.substring(0, 500);
  }

  // === Baidu ===
  console.log('\n=== Baidu 站长 ===');
  const bp = await ctx.newPage();
  await bp.goto('https://ziyuan.baidu.com/site/', { timeout: 15000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 4000));
  console.log('URL:', bp.url().substring(0, 120));
  const btxt = await bp.textContent('body').catch(() => '');
  console.log('Body preview:', btxt.substring(0, 300));
  result.baidu = btxt.substring(0, 500);

  writeFileSync(OUT, JSON.stringify(result, null, 2));
  console.log('\nSaved to', OUT);
  await browser.close();
}

main().catch(e => {
  console.error('Error:', e.message);
  writeFileSync(OUT, JSON.stringify({ error: e.message }, null, 2));
});
