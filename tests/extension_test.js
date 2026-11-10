// Runs extension/bridge.js in a real page with a fake `chrome` API and a fake Flow page.
// node tests/extension_test.js   (needs Playwright; prints OK or throws)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PAGE = `<body>
  <header><button aria-label="Create collection" id="coll">add</button>
          <button aria-label="More options" aria-haspopup="menu" id="more">more_vert</button></header>
  <main><div class="composer"><div><textarea id="box"></textarea></div>
        <div><button aria-label="Add image" id="add">add</button><button id="send">arrow_forward</button></div></div></main>
  <div role="dialog" aria-modal="true" id="dlg" style="display:none">Move collection to trash? This cannot be undone.
        <button id="trash" aria-label="Create">Move to trash</button></div>
  <script>window.clicks = []; for (const b of document.querySelectorAll('button')) b.onclick = () => window.clicks.push(b.id);</script>
</body>`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(PAGE);
  await page.evaluate(() => {
    window.WebSocket = function () { this.readyState = 3; };
    window.fetch = () => Promise.reject(new Error('Failed to fetch'));
    const noop = { addListener() {} };
    window.chrome = {
      runtime: { onStartup: noop, onInstalled: noop, getManifest: () => ({ version: 'test' }) },
      alarms: { onAlarm: noop, create() {} }, action: { onClicked: noop },
      storage: { session: { set: async () => {}, get: async () => ({}) } },
      tabs: { get: async () => ({ url: 'https://flow.google.com/x' }), query: async () => [] },
      scripting: { executeScript: async ({ func, args }) => [{ result: await func(...(args || [])) }] },
    };
    window.setInterval = () => 0;
  });
  const src = fs.readFileSync(path.join(__dirname, '..', 'extension', 'bridge.js'), 'utf8');
  await page.addScriptTag({ content: src.replace('let flowTab = null;', 'let flowTab = 1;') + '\nwindow.bladeRun = run;' });
  const run = (cmd, a) => page.evaluate(([c, x]) => window.bladeRun(c, x || {}).then(r => ({ r }), e => ({ e: e.message })), [cmd, a]);
  const assert = (ok, msg) => { if (!ok) throw new Error('FAILED: ' + msg); };

  let x = await run('type_prompt', { text: 'a red car' });
  assert(x.r && x.r.typed, 'typed');
  x = await run('submit');
  let clicks = await page.evaluate(() => window.clicks);
  assert(x.r.clicked && JSON.stringify(clicks) === '["send"]', 'only the send button next to the prompt box: ' + JSON.stringify([x, clicks]));

  // No send button next to the box: nothing is clicked (before: "Create collection" was).
  await page.evaluate(() => { document.getElementById('send').remove(); window.clicks = []; });
  x = await run('submit');
  clicks = await page.evaluate(() => window.clicks);
  assert(x.r && !x.r.clicked && clicks.length === 0, 'no click elsewhere: ' + JSON.stringify([x, clicks]));

  // A modal dialog is open: typing and submitting are refused, nothing is clicked.
  await page.evaluate(() => { document.getElementById('dlg').style.display = 'block'; });
  for (const cmd of ['type_prompt', 'submit']) {
    x = await run(cmd, { text: 'again' });
    assert(x.e && /dialog/.test(x.e), cmd + ' refused: ' + JSON.stringify(x));
  }
  clicks = await page.evaluate(() => window.clicks);
  assert(clicks.length === 0, 'nothing clicked with a dialog open');
  x = await run('dialog');
  assert(x.r.blocking && /trash/.test(x.r.blocking), 'dialog text is reported');

  // Download: the extension's own fetch fails ("Failed to fetch") -> the page fetch is tried, and a
  // clear message comes back when both fail.
  x = await run('fetch_media', { url: 'https://flow.google.com/fx/api/trpc/media.getMediaUrlRedirect?name=abc' });
  assert(x.e && /Reload the Blade Bridge extension/.test(x.e), 'clear download error: ' + JSON.stringify(x));

  const man = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'extension', 'manifest.json'), 'utf8'));
  assert(man.host_permissions.includes('https://*.googleusercontent.com/*') &&
         man.host_permissions.includes('https://*.googleapis.com/*'), 'host permissions for the media servers');
  await browser.close();
  console.log('OK');
})().catch(e => { console.error(e.message); process.exit(1); });
