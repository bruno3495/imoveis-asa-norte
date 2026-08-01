# -*- coding: utf-8 -*-
"""
Le raw_listings.json, limpa precos invalidos, deduplica (mantendo o MENOR
preco quando e o mesmo imovel) e gera um index.html self-contained com mapa
estilo Airbnb (Leaflet).
"""
import json, re, statistics
from collections import defaultdict

# setores/quadras de Brasilia (Asa Norte e vizinhanca)
_PREF = (r'(SQNW|SQN|SQS|SCLRN|SCLN|SCRN|SHCGN|SHCN|SGAN|SEPN|SHTN|SHLN|SHN|STN|SCEN|'
         r'CLN|EQN|QNL|SCN|SDN|SMDB|QI)')
_RX_NUM = re.compile(r'\b' + _PREF + r'\s*0*(\d{1,3})\b', re.I)
_RX_SEC = re.compile(r'\b' + _PREF + r'\b', re.I)

def extract_quadra(rec):
    """Ex.: 'SQN 214'. Numero quando existir; senao so o setor (hoteleiros)."""
    for src in (rec.get("address") or "", rec.get("title") or ""):
        m = _RX_NUM.search(src)
        if m:
            return f"{m.group(1).upper()} {int(m.group(2))}"
    for src in (rec.get("address") or "", rec.get("title") or ""):
        m = _RX_SEC.search(src)
        if m:
            return m.group(1).upper()
    return None

# limites de sanidade (descarta anuncios com preco claramente invalido)
MIN_VENDA   = 50_000
MIN_ALUGUEL = 400
MAX_VENDA   = 60_000_000     # apto 1-3q acima disso ~ erro/predio inteiro

def load():
    return json.load(open("raw_listings.json", encoding="utf-8"))

def valid_price(x):
    p = x["price"]
    if x["operation"] == "venda":
        return MIN_VENDA <= p <= MAX_VENDA
    return MIN_ALUGUEL <= p <= 100_000

def dedup(items):
    """Agrupa possiveis duplicatas do mesmo imovel e mantem o de menor preco.
    Chave: operacao + quartos + bloco de coordenadas (~110m) + area (~5 m2).
    O registro vencedor guarda em `alt` os links dos demais anuncios do grupo."""
    groups = defaultdict(list)
    for x in items:
        area = x.get("area") or 0
        key = (
            x["operation"],
            int(x["bedrooms"]),
            round(x["lat"], 4),          # ~11 m: mantem predios distintos separados
            round(x["lon"], 4),
            round(area / 2.0) * 2,       # metragem em blocos de 2 m2
        )
        groups[key].append(x)

    result = []
    dup_total = 0
    for key, grp in groups.items():
        grp.sort(key=lambda z: z["price"])
        winner = dict(grp[0])
        others = grp[1:]
        dup_total += len(others)
        winner["dup_count"] = len(others)
        winner["alt"] = [
            {"source": o["source"], "price": o["price"], "url": o["url"]}
            for o in others
        ]
        result.append(winner)
    return result, dup_total

def _quadra_sort_key(q):
    m = re.match(r'([A-Z]+)\s*(\d+)?', q)
    return (m.group(1), int(m.group(2)) if m.group(2) else -1)

def build_html(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    n_venda   = sum(1 for x in data if x["operation"] == "venda")
    n_aluguel = sum(1 for x in data if x["operation"] == "aluguel")
    quadras = sorted({x["quadra"] for x in data if x.get("quadra")}, key=_quadra_sort_key)

    tpl = HTML_TEMPLATE
    tpl = tpl.replace("__DATA__", payload)
    tpl = tpl.replace("__QUADRAS__", json.dumps(quadras, ensure_ascii=False))
    tpl = tpl.replace("__N_TOTAL__", str(len(data)))
    tpl = tpl.replace("__N_VENDA__", str(n_venda))
    tpl = tpl.replace("__N_ALUGUEL__", str(n_aluguel))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(tpl)

def main():
    raw = load()
    clean = [x for x in raw if valid_price(x)]
    deduped, dups = dedup(clean)
    for x in deduped:
        x["quadra"] = extract_quadra(x)
    com_q = sum(1 for x in deduped if x["quadra"])
    print(f"com quadra identificada: {com_q}/{len(deduped)}")
    print(f"brutos: {len(raw)}")
    print(f"apos limpeza de preco: {len(clean)}  (removidos {len(raw)-len(clean)})")
    print(f"apos dedup: {len(deduped)}  (fundidos {dups} duplicados)")
    build_html(deduped)
    print("-> index.html gerado")

# --------------------------------------------------------------- TEMPLATE
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Imóveis Asa Norte · Aluguel & Compra</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<style>
  :root{
    --venda:#2563eb; --venda-d:#1e40af;
    --aluguel:#059669; --aluguel-d:#047857;
    --bg:#f8fafc; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink)}
  #app{display:flex;flex-direction:column;height:100vh}
  header{background:#fff;border-bottom:1px solid var(--line);padding:10px 16px;z-index:1000;box-shadow:0 1px 3px rgba(0,0,0,.06)}
  .row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  h1{font-size:17px;margin:0;font-weight:700;letter-spacing:-.2px}
  h1 small{font-weight:500;color:var(--muted);font-size:12px;margin-left:6px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}
  .seg button{border:0;background:#fff;padding:7px 13px;font-size:13px;font-weight:600;cursor:pointer;color:var(--muted)}
  .seg button.on{color:#fff}
  .seg button.on[data-op="ambos"]{background:#0f172a}
  .seg button.on[data-op="venda"]{background:var(--venda)}
  .seg button.on[data-op="aluguel"]{background:var(--aluguel)}
  .chips{display:inline-flex;gap:6px}
  .chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 12px;font-size:13px;font-weight:600;cursor:pointer;color:var(--muted)}
  .chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
  .fld{display:flex;flex-direction:column;font-size:11px;color:var(--muted);font-weight:600}
  .fld input,.fld select{font-size:13px;padding:5px 8px;border:1px solid var(--line);border-radius:7px;color:var(--ink);font-weight:500}
  .legend{display:inline-flex;gap:14px;font-size:12px;color:var(--muted);align-items:center}
  .legend b{display:inline-flex;align-items:center;gap:5px;font-weight:600;color:var(--ink)}
  .dot{width:11px;height:11px;border-radius:50%;display:inline-block}
  #count{font-size:12px;color:var(--muted);font-weight:600}
  #map{flex:1}
  /* pills estilo airbnb */
  .pill{background:#fff;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:700;white-space:nowrap;
        box-shadow:0 1px 4px rgba(0,0,0,.28);border:1.5px solid transparent;cursor:pointer;transition:transform .08s,box-shadow .08s}
  .pill:hover{transform:scale(1.09);box-shadow:0 3px 10px rgba(0,0,0,.34);z-index:9999}
  .pill.v{color:var(--venda-d);border-color:var(--venda)}
  .pill.a{color:var(--aluguel-d);border-color:var(--aluguel)}
  .pill.sel{color:#fff}
  .pill.v.sel{background:var(--venda);border-color:var(--venda-d)}
  .pill.a.sel{background:var(--aluguel);border-color:var(--aluguel-d)}
  .leaflet-popup-content{margin:0;width:270px!important}
  .leaflet-popup-content-wrapper{border-radius:14px;overflow:hidden;padding:0}
  .pop img{width:100%;height:150px;object-fit:cover;display:block;background:#eee}
  .pop .body{padding:11px 13px 13px}
  .pop .tag{display:inline-block;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.4px;padding:3px 8px;border-radius:6px;color:#fff}
  .pop .price{font-size:19px;font-weight:800;margin:7px 0 2px}
  .pop .price span{font-size:12px;font-weight:600;color:var(--muted)}
  .pop .ttl{font-size:12.5px;line-height:1.35;color:#334155;margin:4px 0 8px;max-height:52px;overflow:hidden}
  .pop .meta{display:flex;gap:10px;font-size:12px;color:var(--muted);font-weight:600;margin-bottom:9px;flex-wrap:wrap}
  .pop a.btn{display:block;text-align:center;background:var(--ink);color:#fff;text-decoration:none;font-weight:700;font-size:13px;padding:9px;border-radius:9px}
  .pop .alt{font-size:11px;color:var(--muted);margin-top:8px;border-top:1px solid var(--line);padding-top:7px}
  .pop .alt a{color:var(--venda);text-decoration:none;font-weight:600}
  .src{font-size:10px;color:var(--muted);font-weight:700;margin-top:7px;text-align:right}
  /* bolhas de agrupamento (nao-pretas) */
  .cl-wrap{background:transparent!important}
  .cl{width:100%;height:100%;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;
      background:rgba(255,255,255,.96);box-shadow:0 2px 9px rgba(0,0,0,.20);font-weight:800;line-height:1;transition:transform .1s}
  .cl:hover{transform:scale(1.07)}
  .cl .n{font-size:14px}
  .cl .u{font-size:8.5px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;opacity:.72;margin-top:2px}
  .cl.v{border:2.5px solid var(--venda);color:var(--venda-d)}
  .cl.a{border:2.5px solid var(--aluguel);color:var(--aluguel-d)}
  /* no modo "Ambos": separa o par compra/aluguel da mesma quadra p/ nao sobrepor */
  #map.split .cl.v{margin:-16px 0 0 -34px}
  #map.split .cl.a{margin:16px 0 0 34px; background:#fff}
  #map.split .cl.a{z-index:1}
  @media(max-width:640px){ h1 small{display:none} .legend{display:none} }
</style>
</head>
<body>
<div id="app">
  <header>
    <div class="row" style="justify-content:space-between">
      <h1>🏙️ Imóveis · Asa Norte <small>Brasília/DF — aluguel & compra</small></h1>
      <div class="legend">
        <b><span class="dot" style="background:var(--venda)"></span>Compra (__N_VENDA__)</b>
        <b><span class="dot" style="background:var(--aluguel)"></span>Aluguel (__N_ALUGUEL__)</b>
      </div>
    </div>
    <div class="row" style="margin-top:9px">
      <div class="seg" id="opSeg">
        <button data-op="ambos" class="on">Ambos</button>
        <button data-op="venda">Comprar</button>
        <button data-op="aluguel">Alugar</button>
      </div>
      <div class="chips" id="bedChips">
        <span class="chip on" data-bed="1">1 quarto</span>
        <span class="chip on" data-bed="2">2 quartos</span>
        <span class="chip on" data-bed="3">3 quartos</span>
      </div>
      <label class="fld">Preço máx (compra)
        <input type="range" id="maxVenda" min="0" max="0" step="50000">
        <span id="maxVendaLbl" style="color:var(--ink)"></span></label>
      <label class="fld">Preço máx (aluguel)
        <input type="range" id="maxAluguel" min="0" max="0" step="500">
        <span id="maxAluguelLbl" style="color:var(--ink)"></span></label>
      <label class="fld">Quadra
        <input id="quadra" list="quadras" placeholder="ex: SQN 214" autocomplete="off" style="width:110px">
        <datalist id="quadras"></datalist></label>
      <label class="fld">Fonte
        <select id="src"><option value="">Todas</option>
          <option value="dfimoveis">DFImóveis</option>
          <option value="wimoveis">Wimóveis</option></select></label>
      <span id="count"></span>
    </div>
  </header>
  <div id="map"></div>
</div>
<script>
const DATA = __DATA__;
const QUADRAS = __QUADRAS__;
const BRL = n => n.toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
function shortPrice(x){
  const p = x.price;
  if(x.operation==='aluguel'){ return p>=1000 ? 'R$ '+(p/1000).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mil' : BRL(p); }
  if(p>=1e6) return 'R$ '+(p/1e6).toLocaleString('pt-BR',{maximumFractionDigits:p>=1e7?0:1})+' mi';
  return 'R$ '+Math.round(p/1000)+' mil';
}
const SRCNAME = {dfimoveis:'DFImóveis', wimoveis:'Wimóveis'};

// hash deterministico -> prioridade estavel em [0,1) p/ amostragem uniforme
function hashPrio(s){ let h=2166136261; for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);} return ((h>>>0)%100000)/100000; }
// leve jitter deterministico p/ separar pills em coordenadas identicas (mesmo predio)
const bucket = {};
DATA.forEach(x=>{
  x._prio = hashPrio(x.source+x.id);
  const k = x.lat.toFixed(5)+','+x.lon.toFixed(5);
  const i = (bucket[k]=(bucket[k]||0)+1)-1;
  if(i>0){ const a=i*2.399, r=0.00016*Math.sqrt(i);
    x._lat=x.lat+r*Math.cos(a); x._lon=x.lon+r*Math.sin(a);
  } else { x._lat=x.lat; x._lon=x.lon; }
});

const map = L.map('map',{zoomControl:true}).setView([-15.762,-47.878],14);
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{
  maxZoom:19, attribution:'© OpenStreetMap © CARTO'}).addTo(map);

// dois grupos separados: compra (azul) e aluguel (verde) -> em "Ambos"
// aparecem duas bolotas na mesma quadra, uma de cada cor.
function makeCluster(kind){       // kind = 'v' | 'a'
  const lbl = kind==='v' ? 'compra' : 'aluguel';
  return L.markerClusterGroup({
    maxClusterRadius: 50,
    showCoverageOnHover: false,
    spiderfyOnMaxZoom: true,
    disableClusteringAtZoom: 18,
    iconCreateFunction: function(c){
      const n = c.getChildCount();
      const size = n<10?36 : n<40?44 : n<120?54 : 64;
      return L.divIcon({
        className:'cl-wrap',
        html:'<div class="cl '+kind+'"><span class="n">'+n+'</span><span class="u">'+lbl+'</span></div>',
        iconSize:[size,size]
      });
    }
  });
}
const clusterV = makeCluster('v').addTo(map);
const clusterA = makeCluster('a').addTo(map);

let selected=null;
function popupHTML(x){
  const col = x.operation==='venda'?'var(--venda)':'var(--aluguel)';
  const tag = x.operation==='venda'?'Compra':'Aluguel';
  const meta=[];
  if(x.quadra) meta.push('📍 '+x.quadra);
  meta.push((x.bedrooms||'?')+' quarto'+(x.bedrooms>1?'s':''));
  if(x.area) meta.push(Math.round(x.area)+' m²');
  if(x.parking) meta.push(x.parking+' vaga'+(x.parking>1?'s':''));
  if(x.bathrooms) meta.push(x.bathrooms+' banh.');
  const condo = x.condo? '<div style="font-size:11px;color:var(--muted)">+ cond. '+BRL(x.condo)+'</div>':'';
  const per = x.operation==='aluguel'?'<span>/mês</span>':'';
  let alt='';
  if(x.alt && x.alt.length){
    alt='<div class="alt">Também anunciado: '+x.alt.map(a=>
      '<a href="'+a.url+'" target="_blank">'+SRCNAME[a.source]+' '+BRL(a.price)+'</a>').join(' · ')+'</div>';
  }
  const img = x.image? '<img src="'+x.image+'" loading="lazy" onerror="this.style.display=\'none\'">':'';
  return '<div class="pop">'+img+'<div class="body">'+
    '<span class="tag" style="background:'+col+'">'+tag+'</span>'+
    '<div class="price">'+BRL(x.price)+per+'</div>'+condo+
    '<div class="ttl">'+(x.title||'').slice(0,110)+'</div>'+
    '<div class="meta">'+meta.map(m=>'<span>'+m+'</span>').join('')+'</div>'+
    '<a class="btn" href="'+x.url+'" target="_blank" rel="noopener">Ver anúncio original ↗</a>'+
    alt+'<div class="src">via '+SRCNAME[x.source]+'</div></div></div>';
}

function makeMarker(x){
  const cls = x.operation==='venda'?'v':'a';
  const icon = L.divIcon({className:'', html:'<div class="pill '+cls+'">'+shortPrice(x)+'</div>', iconSize:null});
  const m = L.marker([x._lat,x._lon],{icon});
  m._data=x;
  m.bindPopup(()=>popupHTML(x),{closeButton:true,autoPan:true});
  m.on('popupopen',e=>{const el=e.target._icon.querySelector('.pill'); if(el)el.classList.add('sel');});
  m.on('popupclose',e=>{const el=e.target._icon&&e.target._icon.querySelector('.pill'); if(el)el.classList.remove('sel');});
  return m;
}

// estado de filtros
const state={op:'ambos',beds:new Set([1,2,3]),src:'',quadra:'',maxV:Infinity,maxA:Infinity};
// popula sugestoes de quadra
document.getElementById('quadras').innerHTML = QUADRAS.map(q=>'<option value="'+q+'">').join('');
const maxVendaAll   = Math.max(...DATA.filter(x=>x.operation==='venda').map(x=>x.price));
const maxAluguelAll = Math.max(...DATA.filter(x=>x.operation==='aluguel').map(x=>x.price));
const rV=document.getElementById('maxVenda'), rA=document.getElementById('maxAluguel');
rV.max=Math.ceil(maxVendaAll/50000)*50000; rV.value=rV.max; state.maxV=+rV.max;
rA.max=Math.ceil(maxAluguelAll/500)*500;   rA.value=rA.max; state.maxA=+rA.max;
document.getElementById('maxVendaLbl').textContent   = BRL(+rV.value);
document.getElementById('maxAluguelLbl').textContent = BRL(+rA.value)+'/mês';

function passes(x){
  if(state.op!=='ambos' && x.operation!==state.op) return false;
  if(!state.beds.has(+x.bedrooms)) return false;
  if(state.src && x.source!==state.src) return false;
  if(state.quadra && !((x.quadra||'').toUpperCase().includes(state.quadra))) return false;
  if(x.operation==='venda' && x.price>state.maxV) return false;
  if(x.operation==='aluguel' && x.price>state.maxA) return false;
  return true;
}
function render(){
  clusterV.clearLayers(); clusterA.clearLayers();
  const vis = DATA.filter(passes);
  const mv=[], ma=[];
  for(const x of vis){ (x.operation==='venda'?mv:ma).push(makeMarker(x)); }
  clusterV.addLayers(mv); clusterA.addLayers(ma);
  document.getElementById('count').textContent = vis.length.toLocaleString('pt-BR')+' imóveis';
}

// UI wiring
const mapEl=document.getElementById('map');
function applySplit(){ mapEl.classList.toggle('split', state.op==='ambos'); }
document.getElementById('opSeg').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b)return;
  state.op=b.dataset.op;
  [...e.currentTarget.children].forEach(c=>c.classList.toggle('on',c===b));
  applySplit(); render();
});
applySplit();
document.getElementById('bedChips').addEventListener('click',e=>{
  const c=e.target.closest('.chip'); if(!c)return;
  const b=+c.dataset.bed;
  if(state.beds.has(b)&&state.beds.size>1){state.beds.delete(b);c.classList.remove('on');}
  else{state.beds.add(b);c.classList.add('on');}
  render();
});
document.getElementById('src').addEventListener('change',e=>{state.src=e.target.value;render();});
document.getElementById('quadra').addEventListener('input',e=>{
  state.quadra=e.target.value.trim().toUpperCase(); render();
  const hit=DATA.filter(passes);
  if(state.quadra && hit.length){ // centraliza na quadra buscada
    const la=hit.reduce((s,x)=>s+x.lat,0)/hit.length, lo=hit.reduce((s,x)=>s+x.lon,0)/hit.length;
    map.setView([la,lo], 16);
  }
});
rV.addEventListener('input',e=>{state.maxV=+e.target.value;document.getElementById('maxVendaLbl').textContent=BRL(state.maxV);render();});
rA.addEventListener('input',e=>{state.maxA=+e.target.value;document.getElementById('maxAluguelLbl').textContent=BRL(state.maxA)+'/mês';render();});

render();
</script>
</body>
</html>"""

if __name__ == "__main__":
    main()
