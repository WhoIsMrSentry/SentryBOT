/* global window, document, fetch, localStorage */
(function(){
  const grid = document.getElementById('grid');
  const q = document.getElementById('q');
  const viewJson = document.getElementById('viewJson');
  const resetLayout = document.getElementById('resetLayout');
  const hl = document.getElementById('hl');
  const lenMap = {};
  const LS_KEY = 'config_center_layout_v1';
  const LS_NOTES = 'config_center_notes_v1';
  const layout = JSON.parse(localStorage.getItem(LS_KEY) || '[]');
  const notes = JSON.parse(localStorage.getItem(LS_NOTES) || '{}');
  const cacheJson = {}; const cacheRaw = {};

  function saveLayout(){
    const kids = grid && grid.children ? Array.prototype.slice.call(grid.children) : [];
    const order = kids.map(e => e.dataset && e.dataset.name).filter(Boolean);
    localStorage.setItem(LS_KEY, JSON.stringify(order));
  }
  function saveNotes(){ localStorage.setItem(LS_NOTES, JSON.stringify(notes)); }
  function escapeHtml(s){
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
  }
  function highlightJsonText(txt){
    let s = escapeHtml(txt);
    s = s.replace(/\"([^\"\\]|\\.)*\"(?=\s*:)/g, m=>'<span class="tok-key">'+m+'</span>');
    s = s.replace(/\"([^\"\\]|\\.)*\"/g, m=>'<span class="tok-str">'+m+'</span>');
    s = s.replace(/\b(true|false)\b/g,'<span class="tok-bool">$1</span>');
    s = s.replace(/\b(null)\b/g,'<span class="tok-null">$1</span>');
    s = s.replace(/(-?\d+(?:\.\d+)?)/g,'<span class="tok-num">$1</span>');
    return s;
  }
  function highlightYamlText(txt){
    let s = escapeHtml(txt);
    s = s.replace(/(^|\n)(\s*#.*)$/g, (_m,a,b)=> a+'<span class="tok-comm">'+b+'</span>');
    s = s.replace(/(^|\n)(\s*)([^:\n]+)(:)/g, (_m,a,b,c,d)=> a+b+'<span class="tok-key">'+c+'</span>'+d);
    s = s.replace(/(\"[^\"]*\"|'[^']*')/g,'<span class="tok-str">$1</span>');
    s = s.replace(/\b(true|false)\b/g,'<span class="tok-bool">$1</span>');
    s = s.replace(/\b(null)\b/g,'<span class="tok-null">$1</span>');
    s = s.replace(/(-?\d+(?:\.\d+)?)/g,'<span class="tok-num">$1</span>');
    return s;
  }

  function makePanel(mod){
    const card = document.createElement('section'); card.className='panel'; card.draggable=true; card.dataset.name=mod.name;
    const title = document.createElement('h3');
    title.innerHTML = `<span>${mod.name}</span><span style="display:flex;gap:6px;align-items:center;"><a class="btn" href='/config/get?module=${mod.name}' target='_blank'>Aç</a></span>`; card.appendChild(title);
    const meta = document.createElement('div'); meta.className='meta'; meta.textContent=mod.path; card.appendChild(meta);
    const tags = document.createElement('div'); tags.className='tags'; (mod.tags||guessTags(mod)).forEach(t=>{ const el=document.createElement('span'); el.className='tag'; el.textContent=t; tags.appendChild(el);}); card.appendChild(tags);
    const actions = document.createElement('div'); actions.className='actions'; actions.innerHTML = `
      <label class='toggle'><input type='checkbox' class='toggleRaw'/> Raw</label>
      <label class='toggle'><input type='checkbox' class='toggleWrap' checked/> Wrap</label>
      <button class='btn btnEdit'>Düzenle</button>
      <button class='btn btnSave' style='display:none'>Kaydet</button>
      <button class='btn btnCancel' style='display:none'>Vazgeç</button>
    `; card.appendChild(actions);
    const pre = document.createElement('pre'); pre.className='code'; pre.textContent='Yükleniyor...'; card.appendChild(pre);
    const editor = document.createElement('textarea'); editor.className='code'; editor.style.display='none'; editor.style.whiteSpace='pre'; editor.style.overflow='hidden'; editor.spellcheck=false; card.appendChild(editor);
    const note = document.createElement('textarea'); note.className='note'; note.placeholder='Yapışkan notlar (yalnızca bu tarayıcıda saklanır)'; note.value = notes[mod.name] || ''; note.addEventListener('input',()=>{ notes[mod.name]=note.value; saveNotes(); }); card.appendChild(note);

    fetchAndRender(pre,mod,actions);
    const toggleRaw = actions.querySelector('.toggleRaw input'); const toggleWrap = actions.querySelector('.toggleWrap input');
    if (toggleRaw) toggleRaw.addEventListener('change', ()=> fetchAndRender(pre,mod,actions));
    if (toggleWrap) toggleWrap.addEventListener('change', ()=>{ pre.style.whiteSpace = toggleWrap.checked ? 'pre-wrap' : 'pre'; });

    const btnEdit=actions.querySelector('.btnEdit'), btnSave=actions.querySelector('.btnSave'), btnCancel=actions.querySelector('.btnCancel');
    if (btnEdit) btnEdit.addEventListener('click', ()=> startEdit(card,mod,pre,editor,actions));
    if (btnSave) btnSave.addEventListener('click', ()=> saveEdit(card,mod,pre,editor,actions));
    if (btnCancel) btnCancel.addEventListener('click', ()=> cancelEdit(card,pre,editor,actions));

    card.addEventListener('dragstart', e=>{ card.classList.add('dragging'); e.dataTransfer.setData('text/plain', mod.name); });
    card.addEventListener('dragend', ()=>{ card.classList.remove('dragging'); saveLayout(); });
    return card;
  }

  function render(){
    grid.innerHTML='';
    const filter=(q&&q.value?q.value:'').toLowerCase();
    const mods=Array.isArray(window.__MODULES__) ? window.__MODULES__ : [];
    let ordered;
    if (layout.length){
      const byLayout=layout.map(name=>mods.find(m=>m&&m.name===name)).filter(Boolean);
      const layoutSet=new Set(layout);
      const rest=mods.filter(m=>m && !layoutSet.has(m.name));
      ordered=byLayout.concat(rest);
    } else ordered=mods;
    ordered = ordered.slice().sort((a,b)=>{
      const la=(a&&lenMap[a.name]!=null)?lenMap[a.name]:Infinity;
      const lb=(b&&lenMap[b.name]!=null)?lenMap[b.name]:Infinity;
      if (la===lb) return String(a.name||'').localeCompare(String(b.name||''),'tr');
      return la-lb;
    });
    const list = ordered.filter(m=>{ if(!m) return false; const tags=Array.isArray(m.tags)?m.tags:[]; const hay=(String(m.name||'')+' '+String(m.path||'')+' '+tags.join(' ')).toLowerCase(); return !filter || hay.includes(filter); });
    list.forEach(m=> grid.appendChild(makePanel(m)));
  }

  function renderContent(pre,obj){
    if (viewJson.checked){ const txt = JSON.stringify(obj,null,2); if (hl && hl.checked) pre.innerHTML = highlightJsonText(txt); else pre.textContent = txt; }
    else { const txt = toYaml(obj); if (hl && hl.checked) pre.innerHTML = highlightYamlText(txt); else pre.textContent = txt; }
    pre.style.maxHeight='none';
  }

  function fetchAndRender(pre,mod,actions){
    if (!actions && pre && pre.parentElement){ actions = pre.parentElement.querySelector('.actions'); }
    let rawChecked=false; if (actions){ const rawInput=actions.querySelector('.toggleRaw input'); rawChecked = rawInput ? !!rawInput.checked : false; }
    if (rawChecked){
      if (cacheRaw.hasOwnProperty(mod.name)){ const txt=cacheRaw[mod.name]; if (hl && hl.checked) pre.innerHTML=highlightYamlText(txt); else pre.textContent=txt; pre.style.maxHeight='none'; }
      else { fetch(`/config/raw?module=${mod.name}`).then(r=>r.text()).then(txt=>{ cacheRaw[mod.name]=txt; lenMap[mod.name]=(txt||'').length; if (hl && hl.checked) pre.innerHTML=highlightYamlText(txt); else pre.textContent=txt; pre.style.maxHeight='none'; }).catch(()=> pre.textContent='Yüklenemedi'); }
    } else {
      if (cacheJson.hasOwnProperty(mod.name)){ renderContent(pre, cacheJson[mod.name]); }
      else { fetch(`/config/get?module=${mod.name}`).then(r=>r.json()).then(obj=>{ cacheJson[mod.name]=obj; renderContent(pre,obj); }).catch(()=> pre.textContent='Yüklenemedi'); }
    }
  }

  const autosaveTimers={};
  function startEdit(card,mod,pre,editor,actions){
    function beginEditWith(text){
      editor.value=text;
      pre.style.display='none';
      editor.style.display='block';
      editor.style.color = getComputedStyle(document.body).getPropertyValue('--text') || '#e5e7eb';
      editor.style.background = '#0b1220';
      function autoSize(){ editor.style.height='auto'; editor.style.height=(editor.scrollHeight+2)+'px'; }
      autoSize(); editor.addEventListener('input', autoSize, { passive: true });
      actions.querySelector('.btnEdit').style.display='none';
      actions.querySelector('.btnSave').style.display='inline-block';
      actions.querySelector('.btnCancel').style.display='inline-block';
      editor.addEventListener('input', ()=>{
        const auto=document.getElementById('autoSave'); if(!auto||!auto.checked) return;
        if (autosaveTimers[mod.name]) clearTimeout(autosaveTimers[mod.name]);
        autosaveTimers[mod.name]=setTimeout(()=>{ saveEdit(card,mod,pre,editor,actions,true); },600);
      }, { passive:true });
    }
    if (cacheRaw.hasOwnProperty(mod.name)) beginEditWith(cacheRaw[mod.name]);
    else fetch(`/config/raw?module=${mod.name}`).then(r=>r.text()).then(txt=>{ cacheRaw[mod.name]=txt; lenMap[mod.name]=(txt||'').length; beginEditWith(txt); }).catch(()=> beginEditWith('# boş'));
  }

  function saveEdit(card,mod,pre,editor,actions,silent){
    silent=!!silent; const payload=editor.value;
    fetch(`/config/set?module=${mod.name}`, { method:'PUT', headers:{'Content-Type':'text/plain'}, body:payload })
      .then(r=>{ if(!r.ok) return r.text().then(t=>Promise.reject(t)); return r.json().catch(()=>({})); })
      .then(()=>{
        delete cacheJson[mod.name]; cacheRaw[mod.name]=payload; lenMap[mod.name]=(payload||'').length;
        fetchAndRender(pre,mod,actions);
        if (!silent){ editor.style.display='none'; pre.style.display='block'; actions.querySelector('.btnEdit').style.display='inline-block'; actions.querySelector('.btnSave').style.display='none'; actions.querySelector('.btnCancel').style.display='none'; }
      })
      .catch(err=> alert('Kaydetme hatası: '+err));
  }

  function cancelEdit(card,pre,editor,actions){ editor.style.display='none'; pre.style.display='block'; actions.querySelector('.btnEdit').style.display='inline-block'; actions.querySelector('.btnSave').style.display='none'; actions.querySelector('.btnCancel').style.display='none'; }

  function guessTags(mod){ const name=mod.name; const tags=[]; if(/cam|camera|vision/.test(name)) tags.push('camera'); if(/neo|pixel|led/.test(name)) tags.push('led'); if(/arduino|serial/.test(name)) tags.push('hardware'); if(/speech|speak|audio/.test(name)) tags.push('audio'); if(/wiki|rag|ollama/.test(name)) tags.push('ai'); if(/diag|health/.test(name)) tags.push('ops'); if(/notify|telegram|discord/.test(name)) tags.push('alerts'); if(!tags.length) tags.push('core'); return tags; }

  function toYaml(obj, indent=0){ const pad='  '.repeat(indent); if(obj===null||obj===undefined) return 'null'; if(typeof obj!=='object') return String(obj); if(Array.isArray(obj)) return obj.map(v=> pad+'- '+toYaml(v, indent+1)).join('\n'); return Object.keys(obj).map(k=> pad+k+': '+(typeof obj[k]==='object' ? '\n'+toYaml(obj[k], indent+1) : toYaml(obj[k],0))).join('\n'); }

  grid.addEventListener('dragover', function(e){ e.preventDefault(); const dragging=document.querySelector('.panel.dragging'); const after=getDragAfterElement(grid,e.clientY); if(!after) grid.appendChild(dragging); else grid.insertBefore(dragging,after); });
  function getDragAfterElement(container,y){ const els=Array.prototype.slice.call(container.querySelectorAll('.panel:not(.dragging)')); let closest={offset:-Infinity,element:null}; for(let i=0;i<els.length;i++){ const child=els[i]; const box=child.getBoundingClientRect(); const offset=y - box.top - box.height/2; if(offset<0 && offset>closest.offset){ closest={offset:offset, element:child}; } } return closest.element; }

  q.addEventListener('input', render);
  viewJson.addEventListener('change', ()=>{ [...grid.querySelectorAll('.code')].forEach(pre=>{ const card=pre.parentElement; const modName=card.dataset.name; if (cacheJson.hasOwnProperty(modName)) renderContent(pre, cacheJson[modName]); else if (cacheRaw.hasOwnProperty(modName)) fetchAndRender(pre,{name:modName}, card.querySelector('.actions')); else fetchAndRender(pre,{name:modName}, card.querySelector('.actions')); }); });
  if (hl) hl.addEventListener('change', ()=>{ render(); });
  if (resetLayout) resetLayout.addEventListener('click', ()=>{ localStorage.removeItem(LS_KEY); location.reload(); });

  const autoScanBtn=document.getElementById('autoScan'); if (autoScanBtn) autoScanBtn.addEventListener('click', ()=> doScan(true));
  function doScan(notify){ fetch('/config/scan',{method:'POST'})
    .then(r=>{ if(!r.ok) return r.text().then(t=>Promise.reject(t)); return r.json(); })
    .then(res=>{ if(res && Array.isArray(res.added)){ res.added.forEach(it=>{ const idx=(window.__MODULES__||[]).findIndex(m=>m&&m.name===it.name); if(idx===-1) window.__MODULES__.push(it); else window.__MODULES__[idx]=it; }); try{ localStorage.removeItem(LS_KEY);}catch{} render(); computeLengths(); if(notify && res.added.length){ alert('Yeni paneller eklendi: '+res.added.length); } } })
    .catch(err=>{ console.error('Scan error', err); alert('Taramada hata: '+err); }); }

  // initial bootstrap
  window.__MODULES__ = [];
  fetch('/config/list').then(r=>r.json()).then(arr=>{ window.__MODULES__ = Array.isArray(arr) ? arr : []; render(); computeLengths(); }).catch(()=>{ render(); computeLengths(); });

  function computeLengths(){ const toFetch=(window.__MODULES__||[]).filter(m=>m && lenMap[m.name]==null); if(!toFetch.length) return; const CHUNK=6; let i=0; function nextBatch(){ const part=toFetch.slice(i,i+CHUNK); if(!part.length){ render(); return; } Promise.allSettled(part.map(m=> fetch(`/config/raw?module=${m.name}`).then(r=>r.text()).then(txt=>{ lenMap[m.name]=(txt||'').length; cacheRaw[m.name]=cacheRaw[m.name]||txt; }))).then(()=>{ i+=CHUNK; nextBatch(); }).catch(()=>{ i+=CHUNK; nextBatch(); }); } nextBatch(); }
})();
