// Node.js script to interact with Chrome DevTools Protocol via WebSocket
const PAGE_WS = 'ws://127.0.0.1:9225/devtools/page/339715803B5FE23841DE6861D547D300';

let msgId = 0;
let ws;

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const handler = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.id === id) resolve(msg);
    };
    ws.on('message', handler);
    ws.send(JSON.stringify({ id, method, params }));
    setTimeout(() => { ws.removeListener('message', handler); reject(new Error('timeout')); }, 10000);
  });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function main() {
  const { default: WebSocket } = await import('ws');
  ws = new WebSocket(PAGE_WS);
  
  await new Promise((resolve, reject) => {
    ws.on('open', resolve);
    ws.on('error', reject);
    setTimeout(() => reject(new Error('WS timeout')), 10000);
  });
  console.log('Connected to page!');

  // Enable Runtime
  await send('Runtime.enable');
  
  // Check page state
  const result = await send('Runtime.evaluate', {
    expression: `(() => {
      const text = document.body?.innerText || '';
      const url = location.href;
      const buttons = Array.from(document.querySelectorAll('button')).map(b => ({ text: b.textContent?.trim(), visible: b.offsetParent !== null }));
      return { url: url.substring(0, 200), text: text.substring(0, 2000), buttons };
    })()`,
    returnByValue: true,
  });
  
  const state = result.result.result.value;
  console.log('\nPage state:', JSON.stringify(state, null, 2));

  // If there's an "Authorize" button, click it
  if (state.text.includes('Authorize') || state.text.includes('授权')) {
    console.log('\nFound authorize page, clicking Authorize...');
    
    const clickResult = await send('Runtime.evaluate', {
      expression: `(() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
          const text = btn.textContent?.trim() || '';
          if ((text.includes('Authorize') || text.includes('授权')) && btn.offsetParent !== null) {
            btn.click();
            return 'clicked: ' + text;
          }
        }
        return 'not found';
      })()`,
      returnByValue: true,
    });
    console.log('Click result:', clickResult.result.result.value);
    
    await sleep(8000);
    
    // Check state after click
    const after = await send('Runtime.evaluate', {
      expression: `JSON.stringify({ url: location.href.substring(0, 200), text: (document.body?.innerText || '').substring(0, 500) })`,
      returnByValue: true,
    });
    console.log('\nAfter authorize:', after.result.result.value);
  } else if (state.text.includes('Sign in to GitHub')) {
    console.log('\nGitHub login page - checking for saved session...');
    
    // Check if there's a "Use password" or passkey option
    const pwdCheck = await send('Runtime.evaluate', {
      expression: `document.body.innerText.includes('Use password') || document.body.innerText.includes('使用密码')`,
      returnByValue: true,
    });
    console.log('Has password option:', pwdCheck.result.result.value);
  }

  ws.close();
}

main().catch(e => { console.error('Error:', e.message); process.exit(1); });
