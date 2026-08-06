// Connect to BROWSER-level WebSocket, create a new tab, navigate to Cloudflare
const WS_URL = 'ws://127.0.0.1:9225/devtools/browser/eca3361a-085a-43aa-8df2-82b03a1b1113';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const ws = new WebSocket(WS_URL);
  
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
    setTimeout(() => reject(new Error('connection timeout')), 10000);
  });
  console.log('Connected to browser!');
  
  let msgId = 0;
  const pending = {};
  
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending[msg.id]) {
      pending[msg.id](msg);
      delete pending[msg.id];
    }
  };
  
  const send = (method, params = {}) => {
    return new Promise((resolve, reject) => {
      const id = ++msgId;
      pending[id] = resolve;
      ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (pending[id]) { delete pending[id]; reject(new Error(`Timeout: ${method}`)); }
      }, 15000);
    });
  };
  
  // Create a new page
  const createResult = await send('Target.createTarget', {
    url: 'about:blank',
    newWindow: false,
    background: true,
  });
  const targetId = createResult.result.targetId;
  console.log('Created target:', targetId);
  
  // Now connect to this page
  // We need to use the page-specific WebSocket URL
  const pageWsUrl = `ws://127.0.0.1:9225/devtools/page/${targetId}`;
  
  // Open a new WebSocket connection to this page
  const pageWs = new WebSocket(pageWsUrl);
  await new Promise((resolve, reject) => {
    pageWs.onopen = resolve;
    pageWs.onerror = reject;
    setTimeout(() => reject(new Error('page WS timeout')), 10000);
  });
  console.log('Connected to new page!');
  
  let pageMsgId = 0;
  const pagePending = {};
  
  pageWs.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pagePending[msg.id]) {
      pagePending[msg.id](msg);
      delete pagePending[msg.id];
    }
  };
  
  const pageSend = (method, params = {}) => {
    return new Promise((resolve, reject) => {
      const id = ++pageMsgId;
      pagePending[id] = resolve;
      pageWs.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (pagePending[id]) { delete pagePending[id]; reject(new Error(`Page timeout: ${method}`)); }
      }, 15000);
    });
  };
  
  // Enable Page and Runtime
  await pageSend('Page.enable');
  await pageSend('Runtime.enable');
  console.log('Page capabilities enabled');
  
  // Navigate to Cloudflare DNS for maref.cc
  console.log('\nNavigating to Cloudflare DNS...');
  const navResult = await pageSend('Page.navigate', {
    url: 'https://dash.cloudflare.com/70625a7eb912b193d7f3d455f9a5916b/dns',
  });
  console.log('Navigation started:', navResult.result);
  
  // Wait for page to load
  await sleep(8000);
  
  // Evaluate page state
  const evalResult = await pageSend('Runtime.evaluate', {
    expression: `document.body?.innerText?.substring(0, 2000) || 'no body'`,
    returnByValue: true,
  });
  console.log('\nPage text:', evalResult.result.result.value?.substring(0, 1000));
  
  // Also check URL
  const urlResult = await pageSend('Runtime.evaluate', {
    expression: `location.href`,
    returnByValue: true,
  });
  console.log('\nCurrent URL:', urlResult.result.result.value);
  
  pageWs.close();
  ws.close();
}

main().catch(e => { console.error('Error:', e.message); process.exit(1); });