# -*- coding: utf-8 -*-
"""
Le raw_listings.json, limpa precos invalidos, deduplica (mantendo o MENOR
preco quando e o mesmo imovel) e gera um index.html self-contained com mapa
estilo Airbnb (Leaflet).
"""
import json, re
from collections import defaultdict
from scrape import REGIONS          # rotulos das regioes (fonte unica de verdade)

# limites de sanidade (descarta anuncios com preco claramente invalido)
MIN_VENDA   = 50_000
MIN_ALUGUEL = 400
# Acima disso e quase sempre erro de digitacao do anunciante (achamos venda de
# R$ 1,8 bi e "aluguel" de R$ 870 mil/mes, que era o valor de venda no campo errado).
MAX_VENDA   = 15_000_000     # p99 real = 2,9 mi
MAX_ALUGUEL = 40_000         # p99 real = 14,5 mil

# setores/quadras do DF
_PREF = (r'(SQNW|SQN|SQS|SCLRN|SCLN|SCRN|SHCGN|SHCS|SHCN|SGAN|SEPN|SHTN|SHLN|SHN|STN|SCEN|'
         r'CLN|CLS|EQN|EQS|QNL|QNM|QNA|QNB|QNC|QND|QNE|QNG|QNJ|QNP|QSA|QSB|QSC|QSD|QI|QL|QE|QS|'
         r'SCN|SDN|SMDB|SMPW|AOS|AE|CA)')
_RX_NUM = re.compile(r'\b' + _PREF + r'\s*0*(\d{1,3})\b', re.I)
_RX_SEC = re.compile(r'\b' + _PREF + r'\b', re.I)

REGION_LABEL = {r["key"]: r["label"] for r in REGIONS}


def extract_quadra(rec):
    """Ex.: 'SQN 214'. Numero quando existir; senao so o setor."""
    for src in (rec.get("address") or "", rec.get("title") or ""):
        m = _RX_NUM.search(src)
        if m:
            return f"{m.group(1).upper()} {int(m.group(2))}"
    for src in (rec.get("address") or "", rec.get("title") or ""):
        m = _RX_SEC.search(src)
        if m:
            return m.group(1).upper()
    return None


def load():
    return json.load(open("raw_listings.json", encoding="utf-8"))


def valid_price(x):
    p = x["price"]
    if x["operation"] == "venda":
        return MIN_VENDA <= p <= MAX_VENDA
    return MIN_ALUGUEL <= p <= MAX_ALUGUEL


# caixa generosa em volta do DF — descarta coordenada zerada/errada do anuncio
DF_BOX = (-16.15, -15.40, -48.40, -47.25)   # lat_min, lat_max, lon_min, lon_max

def valid_geo(x):
    la, lo = x.get("lat"), x.get("lon")
    return (la is not None and lo is not None
            and DF_BOX[0] <= la <= DF_BOX[1] and DF_BOX[2] <= lo <= DF_BOX[3])


def km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * 6371 * asin(sqrt(a))


# Raio maximo (km) do centro da propria regiao, calibrado no percentil 95-99 da
# distribuicao real de cada uma: o Setor Habitacional Jardim Botanico e Sobradinho
# (com Fercal) sao espalhados; Grande Colorado e Guara I sao compactos.
RAIO_REGIAO = {"jardim-botanico": 15, "sobradinho": 18,
               "aguas-claras": 10, "taguatinga": 10, "asa-sul": 9}
RAIO_PADRAO = 8

def drop_outliers(items):
    """Remove anuncio cuja coordenada esta longe demais do centro da sua regiao
    (erro de geocodificacao na origem — ex.: imovel do Grande Colorado marcado
    em Ceilandia). O centro e a MEDIANA da regiao, robusta a esses erros."""
    import statistics
    por_reg = defaultdict(list)
    for x in items:
        por_reg[x.get("region")].append(x)
    out, removidos = [], defaultdict(int)
    for reg, grp in por_reg.items():
        clat = statistics.median([g["lat"] for g in grp])
        clon = statistics.median([g["lon"] for g in grp])
        limite = RAIO_REGIAO.get(reg, RAIO_PADRAO)
        for g in grp:
            if km(clat, clon, g["lat"], g["lon"]) <= limite:
                out.append(g)
            else:
                removidos[reg] += 1
    return out, dict(removidos)


def dedup(items):
    """Agrupa duplicatas do mesmo imovel e mantem o de menor preco.
    Chave: operacao + tipo + quartos + coords (~11 m) + area (±2 m2)."""
    groups = defaultdict(list)
    for x in items:
        area = x.get("area") or 0
        key = (
            x["operation"],
            x.get("kind"),
            int(x["bedrooms"]),
            round(x["lat"], 4),
            round(x["lon"], 4),
            round(area / 2.0) * 2,
        )
        groups[key].append(x)

    result, dup_total = [], 0
    for grp in groups.values():
        grp.sort(key=lambda z: z["price"])
        winner = dict(grp[0])
        others = grp[1:]
        dup_total += len(others)
        winner["alt"] = [{"source": o["source"], "price": o["price"], "url": o["url"]}
                         for o in others]
        result.append(winner)
    return result, dup_total


def compact(x):
    """Payload enxuto: descarta campos nulos e dados so usados no build."""
    rec = {
        "r": x.get("region"),
        "o": "v" if x["operation"] == "venda" else "a",
        "k": x.get("kind"),
        "s": "d" if x["source"] == "dfimoveis" else "w",
        "t": (x.get("title") or "")[:90],
        "u": x.get("url"),
        "p": round(x["price"]),
        "b": int(x["bedrooms"]),
        "lat": round(x["lat"], 5),
        "lon": round(x["lon"], 5),
    }
    for src_key, dst in (("condo", "c"), ("bathrooms", "ba"), ("parking", "v"),
                         ("area", "ar"), ("image", "i"), ("quadra", "q")):
        val = x.get(src_key)
        if val:
            rec[dst] = round(val) if isinstance(val, float) else val
    if x.get("alt"):
        rec["alt"] = [{"s": "d" if a["source"] == "dfimoveis" else "w",
                       "p": round(a["price"]), "u": a["url"]} for a in x["alt"]]
    return rec


def _quadra_sort_key(q):
    m = re.match(r'([A-Z]+)\s*(\d+)?', q)
    return (m.group(1), int(m.group(2)) if m.group(2) else -1)


def build_html(data):
    payload = json.dumps([compact(x) for x in data], ensure_ascii=False,
                         separators=(",", ":"))
    quadras = sorted({x["quadra"] for x in data if x.get("quadra")}, key=_quadra_sort_key)
    # regioes presentes, na ordem do config, com contagem
    counts = defaultdict(int)
    for x in data:
        counts[x.get("region")] += 1
    regioes = [{"key": r["key"], "label": r["label"], "n": counts[r["key"]]}
               for r in REGIONS if counts[r["key"]]]

    tpl = HTML_TEMPLATE
    tpl = tpl.replace("__DATA__", payload)
    tpl = tpl.replace("__REGIOES__", json.dumps(regioes, ensure_ascii=False))
    tpl = tpl.replace("__QUADRAS__", json.dumps(quadras, ensure_ascii=False))
    tpl = tpl.replace("__N_VENDA__", str(sum(1 for x in data if x["operation"] == "venda")))
    tpl = tpl.replace("__N_ALUGUEL__", str(sum(1 for x in data if x["operation"] == "aluguel")))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(tpl)


def main():
    raw = load()
    com_preco = [x for x in raw if valid_price(x)]
    no_df = [x for x in com_preco if valid_geo(x)]
    clean, fora = drop_outliers(no_df)
    deduped, dups = dedup(clean)
    for x in deduped:
        x["quadra"] = extract_quadra(x)

    print(f"brutos: {len(raw)}")
    print(f"apos limpeza de preco: {len(com_preco)}  (removidos {len(raw)-len(com_preco)})")
    print(f"apos filtro geografico: {len(no_df)}  (removidos {len(com_preco)-len(no_df)} fora do DF)")
    if fora:
        print(f"outliers de regiao removidos: {sum(fora.values())} {fora}")
    print(f"apos dedup: {len(deduped)}  (fundidos {dups} duplicados)")
    porreg = defaultdict(int)
    for x in deduped:
        porreg[x.get("region")] += 1
    for r in REGIONS:
        if porreg[r["key"]]:
            print(f"   {r['label']:18s} {porreg[r['key']]:6d}")
    build_html(deduped)
    import os
    print(f"-> index.html gerado ({os.path.getsize('index.html')/1e6:.1f} MB)")


# --------------------------------------------------------------- TEMPLATE
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Imóveis DF · Aluguel & Compra</title>
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
  header{background:#fff;border-bottom:1px solid var(--line);padding:9px 14px;z-index:1000;box-shadow:0 1px 3px rgba(0,0,0,.06)}
  .row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  h1{font-size:16px;margin:0;font-weight:700;letter-spacing:-.2px;white-space:nowrap}
  h1 small{font-weight:500;color:var(--muted);font-size:12px;margin-left:6px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}
  .seg button{border:0;background:#fff;padding:6px 12px;font-size:13px;font-weight:600;cursor:pointer;color:var(--muted)}
  .seg button.on{color:#fff}
  .seg button.on[data-op="ambos"]{background:#0f172a}
  .seg button.on[data-op="venda"]{background:var(--venda)}
  .seg button.on[data-op="aluguel"]{background:var(--aluguel)}
  .chips{display:inline-flex;gap:5px}
  .chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 11px;font-size:12.5px;font-weight:600;cursor:pointer;color:var(--muted);user-select:none}
  .chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
  .fld{display:flex;flex-direction:column;font-size:10.5px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.3px}
  .fld input,.fld select{font-size:13px;padding:5px 7px;border:1px solid var(--line);border-radius:7px;color:var(--ink);font-weight:500;text-transform:none;letter-spacing:0}
  .fld input[type=range]{padding:0;border:0;width:120px}
  .legend{display:inline-flex;gap:12px;font-size:12px;color:var(--muted);align-items:center}
  .legend b{display:inline-flex;align-items:center;gap:5px;font-weight:600;color:var(--ink)}
  .dot{width:11px;height:11px;border-radius:50%;display:inline-block}
  #count{font-size:12.5px;color:var(--ink);font-weight:700}
  #map{flex:1;background:#e8eaed}
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
  .pop .tag2{display:inline-block;font-size:10px;font-weight:700;padding:3px 8px;border-radius:6px;background:#f1f5f9;color:var(--muted);margin-left:4px}
  .pop .price{font-size:19px;font-weight:800;margin:7px 0 2px}
  .pop .price span{font-size:12px;font-weight:600;color:var(--muted)}
  .pop .ttl{font-size:12.5px;line-height:1.35;color:#334155;margin:4px 0 8px;max-height:52px;overflow:hidden}
  .pop .meta{display:flex;gap:9px;font-size:12px;color:var(--muted);font-weight:600;margin-bottom:9px;flex-wrap:wrap}
  .pop a.btn{display:block;text-align:center;background:var(--ink);color:#fff;text-decoration:none;font-weight:700;font-size:13px;padding:9px;border-radius:9px}
  .pop .alt{font-size:11px;color:var(--muted);margin-top:8px;border-top:1px solid var(--line);padding-top:7px}
  .pop .alt a{color:var(--venda);text-decoration:none;font-weight:600}
  .src{font-size:10px;color:var(--muted);font-weight:700;margin-top:7px;text-align:right}
  .cl-wrap{background:transparent!important}
  .cl{width:100%;height:100%;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;
      background:rgba(255,255,255,.96);box-shadow:0 2px 9px rgba(0,0,0,.20);font-weight:800;line-height:1;transition:transform .1s}
  .cl:hover{transform:scale(1.07)}
  .cl .n{font-size:14px}
  .cl .u{font-size:8.5px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;opacity:.72;margin-top:2px}
  .cl.v{border:2.5px solid var(--venda);color:var(--venda-d)}
  .cl.a{border:2.5px solid var(--aluguel);color:var(--aluguel-d)}
  #map.split .cl.v{margin:-16px 0 0 -34px}
  #map.split .cl.a{margin:16px 0 0 34px;background:#fff;z-index:1}
  @media(max-width:700px){ h1 small{display:none} .legend{display:none} }
</style>
</head>
<body>
<div id="app">
  <header>
    <div class="row" style="justify-content:space-between">
      <h1>🏙️ Imóveis DF <small>aluguel & compra · 1 a 3 quartos</small></h1>
      <div class="legend">
        <b><span class="dot" style="background:var(--venda)"></span>Compra (__N_VENDA__)</b>
        <b><span class="dot" style="background:var(--aluguel)"></span>Aluguel (__N_ALUGUEL__)</b>
      </div>
    </div>
    <div class="row" style="margin-top:8px">
      <div class="seg" id="opSeg">
        <button data-op="ambos" class="on">Ambos</button>
        <button data-op="venda">Comprar</button>
        <button data-op="aluguel">Alugar</button>
      </div>
      <label class="fld">Região
        <select id="regiao"><option value="">Todas</option></select></label>
      <div class="chips" id="kindChips">
        <span class="chip on" data-kind="apartamento">Apto</span>
        <span class="chip on" data-kind="casa">Casa</span>
      </div>
      <div class="chips" id="bedChips">
        <span class="chip on" data-bed="1">1q</span>
        <span class="chip on" data-bed="2">2q</span>
        <span class="chip on" data-bed="3">3q</span>
      </div>
      <label class="fld">Preço máx (compra)
        <input type="range" id="maxVenda" min="0" max="0" step="50000">
        <span id="maxVendaLbl" style="color:var(--ink);text-transform:none"></span></label>
      <label class="fld">Preço máx (aluguel)
        <input type="range" id="maxAluguel" min="0" max="0" step="500">
        <span id="maxAluguelLbl" style="color:var(--ink);text-transform:none"></span></label>
      <label class="fld">Quadra
        <input id="quadra" list="quadras" placeholder="ex: SQN 214" autocomplete="off" style="width:105px">
        <datalist id="quadras"></datalist></label>
      <label class="fld">Fonte
        <select id="src"><option value="">Todas</option>
          <option value="d">DFImóveis</option>
          <option value="w">Wimóveis</option></select></label>
      <span id="count"></span>
    </div>
  </header>
  <div id="map"></div>
</div>
<script>
const DATA = __DATA__;
const REGIOES = __REGIOES__;
const QUADRAS = __QUADRAS__;
const RLABEL = {}; REGIOES.forEach(r=>RLABEL[r.key]=r.label);
const SRCNAME = {d:'DFImóveis', w:'Wimóveis'};
const KLABEL  = {apartamento:'Apartamento', casa:'Casa', outro:'Imóvel'};
const BRL = n => n.toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
function shortPrice(x){
  const p = x.p;
  if(x.o==='a'){ return p>=1000 ? 'R$ '+(p/1000).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mil' : BRL(p); }
  if(p>=1e6) return 'R$ '+(p/1e6).toLocaleString('pt-BR',{maximumFractionDigits:p>=1e7?0:1})+' mi';
  return 'R$ '+Math.round(p/1000)+' mil';
}

// jitter deterministico p/ separar anuncios no mesmo ponto (mesmo predio)
const bucket = {};
DATA.forEach(x=>{
  const k = x.lat.toFixed(5)+','+x.lon.toFixed(5);
  const i = (bucket[k]=(bucket[k]||0)+1)-1;
  if(i>0){ const a=i*2.399, r=0.00016*Math.sqrt(i);
    x._lat=x.lat+r*Math.cos(a); x._lon=x.lon+r*Math.sin(a);
  } else { x._lat=x.lat; x._lon=x.lon; }
});

const map = L.map('map',{zoomControl:true, preferCanvas:true}).setView([-15.79,-47.89],11);
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{
  maxZoom:19, attribution:'© OpenStreetMap © CARTO'}).addTo(map);

function makeCluster(kind){
  const lbl = kind==='v' ? 'compra' : 'aluguel';
  return L.markerClusterGroup({
    maxClusterRadius: 50, showCoverageOnHover:false, spiderfyOnMaxZoom:true,
    disableClusteringAtZoom: 18, chunkedLoading:true, chunkInterval:120,
    iconCreateFunction: function(c){
      const n = c.getChildCount();
      const size = n<10?36 : n<40?44 : n<120?54 : n<600?64 : 74;
      return L.divIcon({className:'cl-wrap',
        html:'<div class="cl '+kind+'"><span class="n">'+(n>999?(n/1000).toFixed(1)+'k':n)+'</span><span class="u">'+lbl+'</span></div>',
        iconSize:[size,size]});
    }
  });
}
const clusterV = makeCluster('v').addTo(map);
const clusterA = makeCluster('a').addTo(map);

function popupHTML(x){
  const venda = x.o==='v';
  const col = venda?'var(--venda)':'var(--aluguel)';
  const meta=[];
  if(x.q) meta.push('📍 '+x.q);
  meta.push(x.b+'q');
  if(x.ar) meta.push(x.ar+' m²');
  if(x.v) meta.push(x.v+' vaga'+(x.v>1?'s':''));
  if(x.ba) meta.push(x.ba+' banh.');
  const condo = x.c? '<div style="font-size:11px;color:var(--muted)">+ cond. '+BRL(x.c)+'</div>':'';
  let alt='';
  if(x.alt && x.alt.length){
    alt='<div class="alt">Também anunciado: '+x.alt.map(a=>
      '<a href="'+a.u+'" target="_blank">'+SRCNAME[a.s]+' '+BRL(a.p)+'</a>').join(' · ')+'</div>';
  }
  const img = x.i? '<img src="'+x.i+'" loading="lazy" onerror="this.style.display=\'none\'">':'';
  return '<div class="pop">'+img+'<div class="body">'+
    '<span class="tag" style="background:'+col+'">'+(venda?'Compra':'Aluguel')+'</span>'+
    '<span class="tag2">'+(KLABEL[x.k]||'Imóvel')+' · '+(RLABEL[x.r]||'')+'</span>'+
    '<div class="price">'+BRL(x.p)+(venda?'':'<span>/mês</span>')+'</div>'+condo+
    '<div class="ttl">'+(x.t||'')+'</div>'+
    '<div class="meta">'+meta.map(m=>'<span>'+m+'</span>').join('')+'</div>'+
    '<a class="btn" href="'+x.u+'" target="_blank" rel="noopener">Ver anúncio original ↗</a>'+
    alt+'<div class="src">via '+SRCNAME[x.s]+'</div></div></div>';
}

function makeMarker(x){
  const cls = x.o==='v'?'v':'a';
  const icon = L.divIcon({className:'', html:'<div class="pill '+cls+'">'+shortPrice(x)+'</div>', iconSize:null});
  const m = L.marker([x._lat,x._lon],{icon});
  m.bindPopup(()=>popupHTML(x),{closeButton:true,autoPan:true});
  m.on('popupopen',e=>{const el=e.target._icon&&e.target._icon.querySelector('.pill'); if(el)el.classList.add('sel');});
  m.on('popupclose',e=>{const el=e.target._icon&&e.target._icon.querySelector('.pill'); if(el)el.classList.remove('sel');});
  return m;
}

const state={op:'ambos',beds:new Set([1,2,3]),kinds:new Set(['apartamento','casa','outro']),
             src:'',regiao:'',quadra:'',maxV:Infinity,maxA:Infinity};

document.getElementById('regiao').innerHTML =
  '<option value="">Todas as regiões</option>' +
  REGIOES.map(r=>'<option value="'+r.key+'">'+r.label+' ('+r.n.toLocaleString('pt-BR')+')</option>').join('');
document.getElementById('quadras').innerHTML = QUADRAS.map(q=>'<option value="'+q+'">').join('');

// slider vai ate o percentil 99 (o topo vira "sem limite"), senao um punhado de
// anuncios caros deixaria a faixa util espremida no comeco da barra
function pct99(op){
  const v = DATA.filter(x=>x.o===op).map(x=>x.p).sort((a,b)=>a-b);
  return v.length ? v[Math.floor(v.length*0.99)] : 0;
}
const rV=document.getElementById('maxVenda'), rA=document.getElementById('maxAluguel');
const lblV=document.getElementById('maxVendaLbl'), lblA=document.getElementById('maxAluguelLbl');
rV.max=Math.ceil(pct99('v')/50000)*50000; rV.value=rV.max; state.maxV=Infinity;
rA.max=Math.ceil(pct99('a')/500)*500;     rA.value=rA.max; state.maxA=Infinity;
lblV.textContent='sem limite';
lblA.textContent='sem limite';

function passes(x){
  if(state.op!=='ambos' && (state.op==='venda'?'v':'a')!==x.o) return false;
  if(!state.beds.has(x.b)) return false;
  if(!state.kinds.has(x.k)) return false;
  if(state.regiao && x.r!==state.regiao) return false;
  if(state.src && x.s!==state.src) return false;
  if(state.quadra && !((x.q||'').toUpperCase().includes(state.quadra))) return false;
  if(x.o==='v' && x.p>state.maxV) return false;
  if(x.o==='a' && x.p>state.maxA) return false;
  return true;
}
function render(fit){
  clusterV.clearLayers(); clusterA.clearLayers();
  const vis = DATA.filter(passes);
  const mv=[], ma=[];
  for(const x of vis){ (x.o==='v'?mv:ma).push(makeMarker(x)); }
  clusterV.addLayers(mv); clusterA.addLayers(ma);
  document.getElementById('count').textContent = vis.length.toLocaleString('pt-BR')+' imóveis';
  if(fit && vis.length){
    map.fitBounds(L.latLngBounds(vis.map(x=>[x._lat,x._lon])).pad(0.05));
  }
}

const mapEl=document.getElementById('map');
function applySplit(){ mapEl.classList.toggle('split', state.op==='ambos'); }
document.getElementById('opSeg').addEventListener('click',e=>{
  const b=e.target.closest('button'); if(!b)return;
  state.op=b.dataset.op;
  [...e.currentTarget.children].forEach(c=>c.classList.toggle('on',c===b));
  applySplit(); render();
});
document.getElementById('bedChips').addEventListener('click',e=>{
  const c=e.target.closest('.chip'); if(!c)return;
  const b=+c.dataset.bed;
  if(state.beds.has(b)&&state.beds.size>1){state.beds.delete(b);c.classList.remove('on');}
  else{state.beds.add(b);c.classList.add('on');}
  render();
});
document.getElementById('kindChips').addEventListener('click',e=>{
  const c=e.target.closest('.chip'); if(!c)return;
  const k=c.dataset.kind;
  const on=c.classList.contains('on');
  if(on && state.kinds.size>1){
    state.kinds.delete(k); if(k==='apartamento') state.kinds.delete('outro');
    c.classList.remove('on');
  } else {
    state.kinds.add(k); if(k==='apartamento') state.kinds.add('outro');
    c.classList.add('on');
  }
  render();
});
document.getElementById('regiao').addEventListener('change',e=>{state.regiao=e.target.value;render(true);});
document.getElementById('src').addEventListener('change',e=>{state.src=e.target.value;render();});
document.getElementById('quadra').addEventListener('input',e=>{
  state.quadra=e.target.value.trim().toUpperCase();
  render(!!state.quadra);
});
rV.addEventListener('input',e=>{
  const topo = +e.target.value >= +rV.max;
  state.maxV = topo ? Infinity : +e.target.value;
  lblV.textContent = topo ? 'sem limite' : BRL(state.maxV);
  render();
});
rA.addEventListener('input',e=>{
  const topo = +e.target.value >= +rA.max;
  state.maxA = topo ? Infinity : +e.target.value;
  lblA.textContent = topo ? 'sem limite' : BRL(state.maxA)+'/mês';
  render();
});

applySplit();
render(true);
</script>
</body>
</html>"""

if __name__ == "__main__":
    main()
