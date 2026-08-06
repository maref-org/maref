// Use global WebSocket (available in Node.js 23)
const PAGE_WS = 'ws://127.0.0.1:9225/devtools/page/339715803B5FE23841DE6861D547D300';

const sleep = ms => new Promise(r => setTimeout(r, ms));

function connectCDP(pageWsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(pageWsUrl);
    let msgId = 0;
    const pending = {};
    
    ws.onopen = () => {
      console.log('Connected to page!');
      
      const send = (method, params = {}) => {
        return new Promise((resolveMsg, rejectMsg) => {
          const id = ++msgId;
          pending[id] = resolveMsg;
          ws.send(JSON.stringify({ id, method, params }));
          setTimeout(() => {
            if (pending[id]) {
              delete pending[id];
              rejectMsg(new Error(`Timeout for ${method}`));
            }
          }, 10000);
        });
      };
      
      resolve({ ws, send });
    };
    
    ws.onerror = (err) => reject(err);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && pending[msg.id]) {
        pending[msg.id](msg);
        delete pending[msg.id];
      }
    };
    
    setTimeout(() => reject(new Error('Connection timeout')), 10000);
  });
}

async function main() {
  const { ws, send } = await connectCDP(PAGE_WS);
  
  await send('Runtime.enable');
  
  // Check page state
  const result = await send('Runtime.evaluate', {
    expression: `(() => {
      const text = document.body?.innerText || '';
      const buttons = Array.from(document.querySelectorAll('button')).map(b => ({ 
        text: b.textContent?.trim().substring(0, 60), 
        visible: b.offsetParent !== null 
      }));
      return { 
        url: location.href.substring(0, 200), 
        text: text.substring(0, 2000), 
        buttons: buttons.filter(b => b.visible).slice(0, 10) 
      };
    })()`,
    returnByValue: true,
  });
  
  const state = result.result.result.value;
  console.log('\nPage state:');
  console.log(`  URL: ${state.url}`);
  console.log(`  Text: ${state.text.substring(0, 300)}`);
  console.log(`  Buttons:`, state.buttons);

  // Try to authorize
  if (state.text.includes('Authorize') || state.text.includes('授权')) {
    console.log('\nFound authorize button! Clicking...');
    
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
    
    const after = await send('Runtime.evaluate', {
      expression: `JSON.stringify({ url: location.href.substring(0, 200), text: (document.body?.innerText || '').substring(0, 500) })`,
      returnByValue: true,
    });
    console.log('\nAfter authorize:', after.result.result.value);
  } else {
    console.log('\nNot authorize page - checking login state...');
    
    // Check if already on Cloudflare domain
    const urlCheck = await send('Runtime.evaluate', {
      expression: `location.href`,
      returnByValue: true,
    });
    console.log('Current URL:', urlCheck.result.result.value);
  }

  ws.close();
}

main().catch(e => { console.error('Error:', e.message); }).finally(() => process.exit(0));