import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const CDP = 'http://127.0.0.1:9222';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();

  await page.goto('https://search.google.com/search-console/welcome', {
    timeout: 30000, waitUntil: 'networkidle'
  });
  await sleep(3000);

  // Check frames
  const frames = page.frames();
  console.log(`Frames: ${frames.length}`);
  frames.forEach((f, i) => {
    console.log(`  [${i}] ${f.url().substring(0, 120)}`);
  });

  // Check iframe elements
  const iframes = await page.locator('iframe').count();
  console.log(`\nIframe elements: ${iframes}`);

  for (let i = 0; i < iframes; i++) {
    const src = await page.locator('iframe').nth(i).getAttribute('src');
    console.log(`  Iframe ${i}: src="${src?.substring(0, 120)}"`);
  }

  // Check what content is in the iframe vs main page
  const mainContent = await page.evaluate(() => {
    return {
      bodyChildren: document.body?.children?.length || 0,
      hasAppContent: !!document.querySelector('[role="tabpanel"]'),
      hasMaterialDesign: !!document.querySelector('.U26fgb'),
      hasContinue: document.body.innerText?.includes('继续'),
      iframes: document.querySelectorAll('iframe').length,
      scripts: document.querySelectorAll('script').length,
    };
  });
  console.log('\nMain page:', JSON.stringify(mainContent, null, 2));

  // If there's an iframe with the GSC app, try to interact with it
  if (frames.length > 1) {
    const appFrame = frames.find(f => f.url().includes('search-console') && !f.url().includes('welcome'));
    if (appFrame) {
      console.log(`\nFound app frame: ${appFrame.url()}`);
      const frameContent = await appFrame.textContent().catch(() => '');
      console.log(`Frame content (first 500): ${frameContent.substring(0, 500)}`);
    }
  }

  // Try to interact with the first child frame that has content
  for (const frame of frames.slice(1)) { // skip main page
    if (frame.url() !== 'about:blank') {
      console.log(`\nTrying to interact with frame: ${frame.url().substring(0, 100)}`);
      try {
        const hasInput = await frame.locator('input[aria-label="example.com"]').count();
        console.log(`  Inputs with example.com: ${hasInput}`);

        if (hasInput > 0) {
          await frame.locator('input[aria-label="example.com"]').last().fill('maref.cc');
          console.log('  Filled domain');
          await sleep(500);

          const continueBtn = frame.locator('text=继续').last();
          await continueBtn.click();
          console.log('  Clicked 继续');
          await sleep(3000);
          console.log(`  Frame URL: ${frame.url().substring(0, 120)}`);
        }
      } catch (e) {
        console.log(`  Error: ${e.message}`);
      }
    }
  }

  await browser.close();
}

main().catch(e => console.error('Error:', e.message));
