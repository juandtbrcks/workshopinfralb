let sessionId = null;
let map, layers = {};

// ---------- tabs ----------
document.querySelectorAll('nav button').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('nav button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    ['chat','map','overview'].forEach(t =>
      document.getElementById('tab-'+t).classList.toggle('hide', t !== b.dataset.tab));
    if (b.dataset.tab === 'map') initMap();
    if (b.dataset.tab === 'overview') loadStats();
  };
});

// ---------- health ----------
fetch('/api/health').then(r=>r.json()).then(h=>{
  const el = document.getElementById('health');
  if (h.status === 'ok'){ el.textContent = '🟢 Lakebase conectado'; }
  else { el.textContent = '🟠 modo degradado'; el.title = h.error||''; }
});

// ---------- chat ----------
// Las sugerencias se derivan de los documentos reales de la knowledge base (/api/suggestions).
const sug = document.getElementById('suggest');
fetch('/api/suggestions').then(r=>r.json()).then(j=>{
  (j.sugerencias || []).forEach(s => {
    const c = document.createElement('span');
    c.textContent = s;
    c.onclick = () => { document.getElementById('q').value = s; send(); };
    sug.appendChild(c);
  });
});

function addMsg(text, who, fuentes){
  const log = document.getElementById('log');
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  d.textContent = text;
  if (fuentes && fuentes.length){
    const f = document.createElement('div'); f.className='fuentes';
    fuentes.forEach(x=>{ const c=document.createElement('span'); c.className='chip';
      c.textContent = `${x.doc_id} · ${x.titulo} (${x.sim})`; f.appendChild(c); });
    d.appendChild(f);
  }
  log.appendChild(d); log.scrollTop = log.scrollHeight;
  return d;
}

async function send(){
  const inp = document.getElementById('q');
  const text = inp.value.trim(); if(!text) return;
  inp.value=''; addMsg(text,'user');
  const thinking = addMsg('…','bot');
  try{
    const r = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({session_id: sessionId, message: text})});
    const j = await r.json();
    sessionId = j.session_id;
    thinking.remove();
    addMsg(j.respuesta,'bot', j.fuentes);
  }catch(e){ thinking.textContent = 'Error: '+e; }
}
document.getElementById('send').onclick = send;
document.getElementById('q').addEventListener('keydown', e=>{ if(e.key==='Enter') send(); });

// ---------- map ----------
async function initMap(){
  if (map){ setTimeout(()=>map.invalidateSize(),100); return; }
  map = L.map('map').setView([19.44,-99.14], 10);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    {attribution:'© OpenStreetMap © CARTO', subdomains:'abcd', maxZoom:19}).addTo(map);

  const g = await (await fetch('/api/geo')).json();
  layers.plantas = L.layerGroup().addTo(map);
  layers.clientes = L.layerGroup().addTo(map);
  layers.unidades = L.layerGroup().addTo(map);
  layers.extra = L.layerGroup().addTo(map);

  const selP = document.getElementById('selPlanta');
  const selC = document.getElementById('selCliente');
  g.plantas.forEach(p=>{
    L.circleMarker([p.lat,p.lon],{radius:9,color:'#00a3c4',fillColor:'#00a3c4',fillOpacity:.9})
      .bindPopup(`<b>${p.nombre}</b><br>Planta de llenado<br>${p.capacidad_cilindros_dia} cil/día`).addTo(layers.plantas);
    selP.insertAdjacentHTML('beforeend',`<option value="${p.planta_id}">${p.nombre}</option>`);
  });
  const col = {hospital:'#e74c3c', industria:'#f39c12', distribuidor:'#9b59b6'};
  g.clientes.forEach(c=>{
    L.circleMarker([c.lat,c.lon],{radius:6,color:col[c.tipo]||'#ccc',fillColor:col[c.tipo]||'#ccc',fillOpacity:.85})
      .bindPopup(`<b>${c.nombre}</b><br>${c.tipo} · ${c.segmento}<br>Crédito: ${c.tiene_credito?'sí':'no'}`).addTo(layers.clientes);
    selC.insertAdjacentHTML('beforeend',`<option value="${c.cliente_id}">${c.nombre}</option>`);
  });
  g.unidades.forEach(u=>{
    L.marker([u.lat,u.lon]).bindPopup(`<b>🚚 ${u.placa}</b><br>${u.tipo_unidad} · ${u.capacidad_cilindros} cil`).addTo(layers.unidades);
  });
}

document.getElementById('btnCoverage').onclick = async ()=>{
  layers.extra.clearLayers();
  const planta = document.getElementById('selPlanta').value;
  const km = document.getElementById('radio').value;
  const j = await (await fetch(`/api/geo/coverage?planta_id=${planta}&km=${km}`)).json();
  const g = await (await fetch('/api/geo')).json();
  const p = g.plantas.find(x=>x.planta_id===planta);
  L.circle([p.lat,p.lon],{radius:km*1000,color:'#00a3c4',fillColor:'#00a3c4',fillOpacity:.08}).addTo(layers.extra);
  map.setView([p.lat,p.lon],11);
  document.getElementById('geoResult').innerHTML =
    `<b>${j.clientes.length}</b> clientes dentro de ${km} km de <b>${p.nombre}</b>: `
    + j.clientes.map(c=>`${c.nombre} (${c.km} km)`).join(' · ');
};

document.getElementById('btnNearest').onclick = async ()=>{
  layers.extra.clearLayers();
  const cli = document.getElementById('selCliente').value;
  const j = await (await fetch(`/api/geo/nearest?cliente_id=${cli}`)).json();
  const g = await (await fetch('/api/geo')).json();
  const c = g.clientes.find(x=>x.cliente_id===cli);
  const best = j.plantas[0];
  const p = g.plantas.find(x=>x.nombre===best.nombre);
  L.polyline([[c.lat,c.lon],[p.lat,p.lon]],{color:'#2ecc71',weight:3,dashArray:'6'}).addTo(layers.extra);
  map.fitBounds([[c.lat,c.lon],[p.lat,p.lon]],{padding:[60,60]});
  document.getElementById('geoResult').innerHTML =
    `Planta más cercana a <b>${c.nombre}</b>: <b>${best.nombre}</b> (${best.km} km). `
    + `Alternativas: ` + j.plantas.slice(1).map(x=>`${x.nombre} (${x.km} km)`).join(' · ');
};

// ---------- overview ----------
async function loadStats(){
  const s = await (await fetch('/api/stats')).json();
  const items = [
    ['documentos','Documentos KB'],['clientes','Clientes'],['plantas','Plantas'],
    ['unidades','Unidades'],['pedidos','Pedidos'],['pedidos_en_ruta','En ruta']
  ];
  document.getElementById('stats').innerHTML = items.map(([k,l])=>
    `<div class="card"><div class="n">${s[k]??'—'}</div><div class="l">${l}</div></div>`).join('');
}
