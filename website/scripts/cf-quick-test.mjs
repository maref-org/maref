import { chromium } from 'playwright';

async function main() {
  console.log('Connecting...');
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9225', { timeout: 15000 });
  console.log('Connected!');
  
  // List pages from existing context
  const pages = browser.contexts()[0]?.pages() || [];
  console.log(`Pages: ${pages.length}`);
  for (const p of pages) {
    const url = p.url().substring(0, 100);
    console.log(`  ${url}`);
  }
  
  // Create a new page
  console.log('Creating new page...');
  const page = await browser.contexts()[0].newPage();
  console.log('New page created!');
  
  await page.goto('about:blank', { timeout: 5000 });
  console.log('Navigated to about:blank');
  
  await browser.close();
  console.log('Done!');
}

main().catch(e => console.error('Error:', e.message));
