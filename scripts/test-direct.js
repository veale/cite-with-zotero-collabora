// Paste into DevTools console when the context dropdown is set to the Collabora frame
// (window.location.href should show localhost:9980/browser/.../cool.html)
//
// Since we're already inside the Collabora frame, postMessage goes to window (self).
// Collabora's Map.WOPI.js handler receives it, runs the Python script via UNO,
// then postMessages the result back to e.source (also window).

const win = window;

function typedArgs(obj) {
  if (!obj || Object.keys(obj).length === 0) return null;
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'boolean')                       out[k] = { type: 'boolean', value: v };
    else if (typeof v === 'number' && v === (v | 0)) out[k] = { type: 'long',    value: v };
    else                                              out[k] = { type: 'string',  value: String(v) };
  }
  return out;
}

function send(scriptFile, fn, args = {}) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timeout: ${fn}`)), 15_000);
    function handler(e) {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.MessageId !== 'CallPythonScript-Result') return;
      clearTimeout(timeout);
      window.removeEventListener('message', handler);
      if (msg.Values?.success !== 'true') {
        reject(new Error(`${fn} failed: ${JSON.stringify(msg.Values)}`));
        return;
      }
      resolve(msg.Values.result.value);
    }
    window.addEventListener('message', handler);
    win.postMessage(JSON.stringify({
      MessageId:  'CallPythonScript',
      SendTime:   Date.now(),
      ScriptFile: scriptFile,
      Function:   fn,
      Values:     typedArgs(args),
    }), '*');
  });
}

const f  = (fn, args) => send('zotero_fields.py', fn, args);
const ex = (fn, args) => send('zotero_export.py', fn, args);

async function runTests() {
  console.log('=== Phase 2 gate: Python round-trip ===');

  let r = await f('getDocumentData');
  console.log('1. getDocumentData:', r);

  await f('setDocumentData', { data: 'http://zotero.org/styles/apa' });
  r = await f('getDocumentData');
  console.log(`2. setDocumentData: ${r?.includes('apa') ? '✓' : '✗ FAIL'}`, r);

  r = await f('insertField', { fieldType: 'Bookmark', noteType: 0 });
  const field = JSON.parse(r);
  console.log('3. insertField:', field);
  if (!field?.fieldID) { console.error('FAIL: no fieldID'); return; }
  const { fieldID } = field;

  await f('setFieldCode', { fieldID, code: 'ZOTERO_ITEM CSL_CITATION {"citationID":"t1","citationItems":[{"id":1,"itemData":{"type":"article-journal","title":"Test","author":[{"family":"Smith","given":"A"}],"issued":{"date-parts":[[2024]]}}}]}' });
  console.log('4. setFieldCode: ✓');

  await f('setFieldText', { fieldID, text: '(Smith, 2024)', isRich: false });
  console.log('5. setFieldText: ✓');

  r = await f('getFields', { fieldType: 'Bookmark' });
  const fields = JSON.parse(r);
  console.log(`6. getFields: ${fields?.fieldIDs?.includes(fieldID) ? '✓' : '✗ FAIL'}`, fields);

  r = await f('cursorInField', { fieldType: 'Bookmark' });
  console.log('7. cursorInField:', JSON.parse(r));

  r = await ex('exportCitations', { format: 'csljson' });
  console.log('8. exportCitations:', JSON.parse(r));

  console.log('=== Done ===');
}

runTests().catch(console.error);
