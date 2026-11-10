// Blade Bridge: lets the Blade Editor app on this computer (ws://127.0.0.1) drive Google Flow
// in this Chrome, with your own login. It only acts on Flow tabs and never approves credits.
const PORT = 17321;
let ws = null;
let flowTab = null;

let checking = false;

async function connect() {
  if (ws && ws.readyState <= 1) return;
  if (checking) return;
  // Ask quietly first: a failed fetch is not reported, a failed WebSocket shows up in
  // chrome://extensions as "ERR_CONNECTION_REFUSED" every time Blade is not running.
  checking = true;
  try {
    await fetch(`http://127.0.0.1:${PORT}/`, { mode: 'no-cors', cache: 'no-store' });
  } catch (e) {
    return;  // Blade is not running now; try again later
  } finally {
    checking = false;
  }
  if (ws && ws.readyState <= 1) return;
  try { ws = new WebSocket(`ws://127.0.0.1:${PORT}`); } catch (e) { ws = null; return; }
  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);
    if (!msg.id) return;
    let reply;
    try { reply = { id: msg.id, ok: true, result: await run(msg.cmd, msg.args || {}) }; }
    catch (e) { reply = { id: msg.id, ok: false, error: String((e && e.message) || e) }; }
    ws.send(JSON.stringify(reply));
  };
  ws.onclose = () => { ws = null; };
  ws.onerror = () => {};
}

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create('blade', { periodInMinutes: 0.5 }); connect(); });
chrome.alarms.onAlarm.addListener(connect);
chrome.action.onClicked.addListener(connect);
// While connected, a ping every 20 s keeps the extension awake; while not, a quiet check every 5 s.
let ticks = 0;
setInterval(() => { ticks++; if (ws && ws.readyState === 1) { if (ticks % 4 === 0) ws.send('{"ping":1}'); } else connect(); }, 5000);
connect();

const DEFAULT_PREFIXES = ['https://flow.google.com/', 'https://labs.google/fx/tools/flow'];

// Chrome puts an idle MV3 service worker to sleep and its variables are lost, so the Flow tab id
// is kept in chrome.storage.session; if that tab is gone, the Flow tab is found again by its URL.
async function rememberTab(id, prefixes) {
  flowTab = id;
  await chrome.storage.session.set(prefixes ? { flowTab: id, prefixes } : { flowTab: id });
}

async function findFlowTab() {
  if (flowTab !== null) {
    try { await chrome.tabs.get(flowTab); return flowTab; } catch (e) { flowTab = null; }
  }
  const s = await chrome.storage.session.get(['flowTab', 'prefixes']);
  if (s.flowTab !== undefined) {
    try { await chrome.tabs.get(s.flowTab); flowTab = s.flowTab; return flowTab; } catch (e) {}
  }
  const prefixes = s.prefixes || DEFAULT_PREFIXES;
  const t = (await chrome.tabs.query({})).find(x => x.url && prefixes.some(p => x.url.startsWith(p)));
  if (t) { await rememberTab(t.id); return t.id; }
  return null;
}

async function inTab(func, args = [], world = 'ISOLATED') {
  const res = await chrome.scripting.executeScript({ target: { tabId: flowTab, allFrames: true }, func, args, world });
  return res.map(r => r.result);
}

function waitComplete(tabId) {
  return new Promise(resolve => {
    const check = (id, info) => {
      if (id === tabId && info.status === 'complete') { chrome.tabs.onUpdated.removeListener(check); resolve(); }
    };
    chrome.tabs.onUpdated.addListener(check);
    setTimeout(() => { chrome.tabs.onUpdated.removeListener(check); resolve(); }, 60000);
  });
}

// A modal dialog (e.g. "Move collection to trash?") that does not hold the prompt box. While one is
// open, Blade types nothing and clicks nothing: the user answers it in Chrome.
function blockingDialog() {
  const vis = (el) => el && el.offsetParent !== null;
  const box = [...document.querySelectorAll('[contenteditable="true"], textarea')].find(vis);
  const d = [...document.querySelectorAll('[role="alertdialog"], [role="dialog"][aria-modal="true"], dialog[open]')]
    .find(el => vis(el) && !(box && el.contains(box)));
  return d ? (d.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 160) || 'dialog' : null;
}

async function refuseIfDialog() {
  const d = (await inTab(blockingDialog)).find(Boolean);
  if (d) throw new Error('Flow shows a dialog ("' + d + '"). Blade does not click dialogs: answer or close it in Chrome, then try again.');
}

async function run(cmd, a) {
  if (cmd === 'hello') return { version: chrome.runtime.getManifest().version };

  if (cmd === 'ensure_tab') {
    const tabs = await chrome.tabs.query({});
    // Flow moved from labs.google/fx/tools/flow to flow.google.com: accept every given prefix.
    const prefixes = [].concat(a.match);
    const t = tabs.find(x => x.url && prefixes.some(p => x.url.startsWith(p)));
    if (t) { await rememberTab(t.id, prefixes); return { url: t.url, opened: false }; }
    const n = await chrome.tabs.create({ url: a.url, active: true });
    await rememberTab(n.id, prefixes);
    await waitComplete(n.id);
    return { url: (await chrome.tabs.get(n.id)).url || a.url, opened: true };
  }
  if (await findFlowTab() === null) throw new Error('No Flow tab is open in Chrome (open flow.google.com).');

  if (cmd === 'type_prompt') {
    await refuseIfDialog();
    const r = await inTab((text) => {
      const vis = (el) => el && el.offsetParent !== null;
      const box = [...document.querySelectorAll('[contenteditable="true"], textarea')].find(vis);
      if (!box) return false;
      box.focus();
      if (box.tagName === 'TEXTAREA') {
        const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
        set.call(box, text);
        box.dispatchEvent(new Event('input', { bubbles: true }));
      } else {
        document.execCommand('selectAll', false);
        document.execCommand('insertText', false, text);
      }
      return true;
    }, [a.text]);
    return { typed: r.some(Boolean) };
  }

  if (cmd === 'attach_images') {
    // Start/end frames: Flow's upload control is not documented, so try the usual ways in order:
    // a file <input>, a paste into the prompt box, a drop onto it. Credits are never involved.
    const r = await inTab(async (files) => {
      const list = files.map(f => {
        const bin = atob(f.b64), u8 = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        return new File([u8], f.name, { type: f.type });
      });
      const dt = () => { const d = new DataTransfer(); list.forEach(f => d.items.add(f)); return d; };
      const inputs = [...document.querySelectorAll('input[type="file"]')];
      const input = inputs.find(i => /image/.test(i.accept || '')) || inputs[0];
      if (input) {
        if (!input.multiple && list.length > 1) {
          for (const f of list) {  // one file per change event
            const d = new DataTransfer(); d.items.add(f); input.files = d.files;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            await new Promise(ok => setTimeout(ok, 800));
          }
        } else {
          input.files = dt().files;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return 'file-input';
      }
      const vis = (el) => el && el.offsetParent !== null;
      const box = [...document.querySelectorAll('[contenteditable="true"], textarea')].find(vis);
      if (!box) return null;
      box.focus();
      const pasted = !box.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt(), bubbles: true, cancelable: true }));
      if (pasted) return 'paste';
      for (const type of ['dragenter', 'dragover', 'drop']) {
        box.dispatchEvent(new DragEvent(type, { dataTransfer: dt(), bubbles: true, cancelable: true }));
      }
      return 'drop';
    }, [a.files], 'MAIN');  // the page's own world: its upload handlers see the files and events
    return { method: r.find(Boolean) || null };
  }

  if (cmd === 'submit') {
    // Only the send button that belongs to the prompt box is clicked. Before 1.0.6 the first button
    // on the page with "create" in its label was clicked: that made an "Untitled collection" and
    // opened a "Move collection to trash?" dialog.
    await refuseIfDialog();
    const r = await inTab(() => {
      const vis = (el) => el && el.offsetParent !== null && !el.disabled;
      const box = [...document.querySelectorAll('[contenteditable="true"], textarea')].find(vis);
      if (!box) return { clicked: false, why: 'no prompt box' };
      const label = (b) => ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).trim();
      const icons = ['arrow_forward', 'arrow_upward', 'send'];
      const good = /\b(generate|create|send|submit)\b/i;
      // Never: menus, collections, projects, delete/trash, downloads, sharing, uploads, settings.
      const bad = /collection|trash|delete|remove|discard|project|folder|more|menu|option|setting|share|download|upload|add|attach|new|close|cancel|back|edit|rename|expand|tune|mode|model/i;
      const ok = (b) => vis(b) && !b.getAttribute('aria-haspopup') && !bad.test(label(b)) &&
        (icons.includes((b.innerText || '').trim()) || good.test(b.getAttribute('aria-label') || ''));
      // Walk up from the prompt box: the nearest container that holds a send button (at most 6 levels).
      let node = box.parentElement;
      for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
        const found = [...node.querySelectorAll('button')].filter(ok);
        if (found.length === 1) { found[0].click(); return { clicked: true, label: label(found[0]).slice(0, 40) }; }
        if (found.length > 1) return { clicked: false, why: 'more than one possible send button: ' + found.map(b => label(b).slice(0, 30)).join(' | ') };
      }
      return { clicked: false, why: 'no send button next to the prompt box' };
    });
    const hit = r.find(x => x && x.clicked);
    return hit || { clicked: false, why: (r.find(x => x && x.why) || {}).why || 'no prompt box' };
  }

  if (cmd === 'scan') {
    const r = await inTab(() => [...document.querySelectorAll('video, img')].map(el => ({
      tag: el.tagName, src: el.currentSrc || el.src || '', poster: el.getAttribute('poster') || '',
      w: el.width || el.clientWidth || 0 })));
    return { items: r.flat().filter(Boolean) };
  }

  if (cmd === 'probe') {
    // What the Flow page shows: a prompt box means a project is open (home page has none).
    const r = await inTab(() => {
      const vis = (el) => el && el.offsetParent !== null;
      return {
        prompt_box: [...document.querySelectorAll('[contenteditable="true"], textarea')].some(vis),
        title: document.title,
        buttons: [...document.querySelectorAll('button, a[role="button"]')].filter(vis)
          .map(b => (b.getAttribute('aria-label') || b.innerText || '').trim().slice(0, 40)).filter(Boolean).slice(0, 20),
      };
    });
    const tab = await chrome.tabs.get(flowTab);
    return Object.assign({ url: tab.url }, r.find(x => x && x.prompt_box) || r[0] || {});
  }

  if (cmd === 'dialog') {
    const r = await inTab(() => [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')]
      .some(el => el.offsetParent !== null));
    return { open: r.some(Boolean), blocking: (await inTab(blockingDialog)).find(Boolean) || null };
  }

  if (cmd === 'fetch_media') {
    if (a.url.startsWith('blob:')) {
      const r = await inTab(async (u) => {
        try {
          const b = await (await fetch(u)).blob();
          return await new Promise(ok => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(b); });
        } catch (e) { return null; }
      }, [a.url]);
      const d = r.find(Boolean);
      if (!d) throw new Error('Could not read the blob video.');
      return { type: d.slice(5, d.indexOf(';')), b64: d.split(',', 2)[1] };
    }
    // Flow's media address redirects to another Google server (googleusercontent / googleapis):
    // the extension needs host permission for it (manifest 1.0.6), else "Failed to fetch".
    let resp, first;
    try {
      resp = await fetch(a.url, { credentials: 'include' });
    } catch (e) { first = String((e && e.message) || e); }
    if (resp) {
      const buf = new Uint8Array(await resp.arrayBuffer());
      let bin = '';
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
      return { status: resp.status, type: resp.headers.get('content-type') || '', b64: btoa(bin) };
    }
    // Second way: fetch inside the Flow page itself (its own login and origin).
    const r = await inTab(async (u) => {
      try {
        const res = await fetch(u, { credentials: 'include' });
        const b = await res.blob();
        const d = await new Promise(ok => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(b); });
        return { status: res.status, type: b.type || '', d };
      } catch (e) { return { error: String((e && e.message) || e) }; }
    }, [a.url], 'MAIN');
    const hit = r.find(x => x && x.d);
    if (!hit) throw new Error('Could not download the clip (' + first + '; in the page: ' + ((r.find(x => x && x.error) || {}).error || 'no result') +
                              '). Reload the Blade Bridge extension in chrome://extensions (version 1.0.6 or newer) and call flow_collect again.');
    return { status: hit.status, type: hit.type, b64: hit.d.split(',', 2)[1] };
  }

  if (cmd === 'screenshot') {
    const tab = await chrome.tabs.get(flowTab);
    await chrome.tabs.update(flowTab, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
    if (tab.status !== 'complete') await waitComplete(flowTab);
    let d;
    try {
      d = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 60 });
    } catch (e) {
      throw new Error('Chrome allows the screenshot only after you click the Blade Bridge icon once ' +
                      'while the Flow tab is open (then it works until the tab is closed or reloaded). ' + e.message);
    }
    return { b64: d.split(',', 2)[1] };
  }

  throw new Error('Unknown command ' + cmd);
}
