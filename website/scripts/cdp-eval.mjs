// Connect to CDP directly via WebSocket and evaluate a page
const WS_URL = 'ws://127.0.0.1:9225/devtools/browser/eca3361a-085a-43aa-8df2-82b03a1b1113';

// Use node's built-in fetch for the /json endpoint
async function getTargets() {
  const resp = await fetch('http://127.0.0.1:9225/json');
  return resp.json();
}

async function main() {
  const targets = await getTargets();
  
  // Find the GitHub OAuth page
  const githubPage = targets.find(t => t.url.includes('github.com/login/oauth'));
  if (!githubPage) {
    console.log('No GitHub OAuth page found');
    return;
  }
  
  console.log('GitHub OAuth page:');
  console.log(`  URL: ${githubPage.url.substring(0, 200)}`);
  console.log(`  Title: ${githubPage.title}`);
  console.log(`  WS: ${githubPage.webSocketDebuggerUrl.substring(0, 80)}`);
}

main().catch(e => console.error('Error:', e.message));
