# -*- coding: utf-8 -*-
"""
Gera analise.html — analise exploratoria (EDA) dos imoveis coletados.
Usa a mesma limpeza do build.py (preco, geografia, outliers, dedup).
"""
import json, os, statistics as st, datetime
from collections import Counter, defaultdict
from scrape import REGIONS
from build import (valid_price, valid_geo, drop_outliers, dedup,
                   extract_quadra, snap_para_quadra)

AREA_MIN, AREA_MAX = 20, 2000        # area plausivel p/ calcular R$/m2


def med(v):
    return st.median(v) if v else None


def m2_de(items, kind=None):
    """R$/m² dos itens, opcionalmente so de um tipo (casa distorce: a area inclui lote)."""
    return [x["price"] / x["area"] for x in items
            if x.get("area") and AREA_MIN < x["area"] < AREA_MAX
            and (kind is None or x["kind"] == kind)]


def carregar():
    """Mesmo pipeline do build.py — inclusive o reposicionamento pelo endereco,
    para que os centros de quadra do mapa de calor batam com os do mapa."""
    raw = json.load(open("raw_listings.json", encoding="utf-8"))
    d = [x for x in raw if valid_price(x) and valid_geo(x)]
    d, _ = drop_outliers(d)
    for x in d:
        x["quadra"] = extract_quadra(x)
    snap_para_quadra(d)
    d, dups = dedup(d)
    return raw, d, dups


def hist(vals, nbins=22):
    """Histograma entre p1 e p99 (evita a cauda esticar tudo)."""
    if not vals:
        return {"bins": [], "max": 0}
    v = sorted(vals)
    lo, hi = v[int(len(v) * .01)], v[int(len(v) * .99)]
    if hi <= lo:
        hi = lo + 1
    w = (hi - lo) / nbins
    counts = [0] * nbins
    for x in v:
        if x < lo or x > hi:
            continue
        i = min(nbins - 1, int((x - lo) / w))
        counts[i] += 1
    return {"bins": [{"x0": lo + i * w, "x1": lo + (i + 1) * w, "n": c}
                     for i, c in enumerate(counts)],
            "max": max(counts) if counts else 0,
            "fora": sum(1 for x in v if x < lo or x > hi)}


def main():
    raw, d, dups = carregar()
    venda   = [x for x in d if x["operation"] == "venda"]
    aluguel = [x for x in d if x["operation"] == "aluguel"]

    m2 = m2_de

    regioes = []
    for r in REGIONS:
        k = r["key"]
        v = [x for x in venda if x["region"] == k]
        a = [x for x in aluguel if x["region"] == k]
        mv, ma = med([x["price"] for x in v]), med([x["price"] for x in a])
        regioes.append({
            "key": k, "label": r["label"],
            "n": len(v) + len(a), "n_venda": len(v), "n_aluguel": len(a),
            "med_venda": mv, "med_aluguel": ma,
            # R$/m2 apenas de APARTAMENTOS: em casa a area inclui lote e a
            # comparacao entre regioes fica distorcida.
            "m2_venda": med(m2(v, "apartamento")),
            "m2_aluguel": med(m2(a, "apartamento")),
            "area": med([x["area"] for x in v if x.get("area") and AREA_MIN < x["area"] < AREA_MAX]),
            # rentabilidade anual bruta implicita (medianas de conjuntos diferentes)
            "yield": (ma * 12 / mv * 100) if (mv and ma) else None,
            "yield_confiavel": len(a) >= 30,
            "casas": sum(1 for x in v + a if x["kind"] == "casa"),
        })

    quartos = []
    for kind in ("apartamento", "casa"):
        for b in (1, 2, 3):
            v = [x["price"] for x in venda if x["kind"] == kind and x["bedrooms"] == b]
            a = [x["price"] for x in aluguel if x["kind"] == kind and x["bedrooms"] == b]
            quartos.append({"kind": kind, "b": b, "n_venda": len(v), "n_aluguel": len(a),
                            "med_venda": med(v), "med_aluguel": med(a)})

    # data da COLETA (nao a de geracao da pagina): so assim o rodape nao promete
    # dados de hoje quando o build roda sobre uma coleta antiga
    coletado = None
    if os.path.exists("raw_meta.json"):
        try:
            coletado = json.load(open("raw_meta.json", encoding="utf-8")).get("coletado_em")
        except Exception:
            coletado = None
    if not coletado:
        coletado = datetime.date.fromtimestamp(
            os.path.getmtime("raw_listings.json")).isoformat()

    # --- agregado por quadra, para o mapa de calor ---
    por_q = defaultdict(list)
    for x in d:
        if x.get("quadra") and any(c.isdigit() for c in x["quadra"]):
            por_q[(x["quadra"], x["region"])].append(x)
    quadras = []
    for (q, reg), g in por_q.items():
        if len(g) < 3:                       # amostra minima p/ uma cor honesta
            continue
        v = [x for x in g if x["operation"] == "venda"]
        m2q = med(m2_de(v, "apartamento"))
        quadras.append({
            "q": q, "r": reg, "n": len(g),
            "lat": round(st.median([x["lat"] for x in g]), 5),
            "lon": round(st.median([x["lon"] for x in g]), 5),
            "m2": round(m2q) if m2q else None,
            "med": round(med([x["price"] for x in v])) if v else None,
            "nv": len(v),
        })
    quadras.sort(key=lambda z: -(z["m2"] or 0))

    dados = {
        "gerado": coletado,
        "quadras": quadras,
        "kpi": {
            "total": len(d), "venda": len(venda), "aluguel": len(aluguel),
            "med_venda": med([x["price"] for x in venda]),
            "med_aluguel": med([x["price"] for x in aluguel]),
            "m2_venda": med(m2(venda, "apartamento")),
            "regioes": len(regioes), "brutos": len(raw), "dups": dups,
        },
        "regioes": regioes,
        "quartos": quartos,
        "hist_venda": hist([x["price"] for x in venda]),
        "hist_aluguel": hist([x["price"] for x in aluguel]),
        "hist_area": hist([x["area"] for x in d if x.get("area") and AREA_MIN < x["area"] < AREA_MAX]),
        "tipo": dict(Counter(x["kind"] for x in d)),
        "fonte": dict(Counter(x["source"] for x in d)),
        "quartos_dist": dict(Counter(x["bedrooms"] for x in d)),
    }

    html = TEMPLATE.replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
    open("analise.html", "w", encoding="utf-8").write(html)
    print(f"-> analise.html gerado ({os.path.getsize('analise.html')/1024:.0f} KB)")
    print(f"   {len(d)} imoveis | {len(venda)} venda | {len(aluguel)} aluguel")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Análise · Imóveis DF</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  color-scheme: light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --venda:#2a78d6; --aluguel:#1baf7a; --casa:#eb6834;
  --seq-100:#cde2fb; --seq-250:#86b6ef; --seq-450:#2a78d6; --seq-600:#184f95;
  --warn:#fab219;
}
@media (prefers-color-scheme: dark){
  :root:where(:not([data-theme="light"])){
    color-scheme: dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --text-primary:#fff; --text-secondary:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
    --venda:#3987e5; --aluguel:#199e70; --casa:#d95926;
    --seq-100:#184f95; --seq-250:#1c5cab; --seq-450:#3987e5; --seq-600:#86b6ef;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface-1:#1a1a19; --plane:#0d0d0d;
  --text-primary:#fff; --text-secondary:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --venda:#3987e5; --aluguel:#199e70; --casa:#d95926;
  --seq-100:#184f95; --seq-250:#1c5cab; --seq-450:#3987e5; --seq-600:#86b6ef;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
header{background:var(--surface-1);border-bottom:1px solid var(--border);padding:12px 20px;
  position:sticky;top:0;z-index:10}
.hrow{display:flex;align-items:center;gap:16px;flex-wrap:wrap;max-width:1180px;margin:0 auto}
h1{font-size:17px;margin:0;font-weight:700;letter-spacing:-.2px}
h1 small{font-weight:500;color:var(--text-secondary);font-size:12px;margin-left:6px}
nav{display:inline-flex;border:1px solid var(--border);border-radius:9px;overflow:hidden;margin-left:auto}
nav a{padding:7px 15px;font-size:13px;font-weight:700;text-decoration:none;color:var(--text-secondary);background:var(--surface-1)}
nav a.on{background:var(--venda);color:#fff}
main{max-width:1180px;margin:0 auto;padding:20px}
section{background:var(--surface-1);border:1px solid var(--border);border-radius:14px;
  padding:18px 20px 20px;margin-bottom:16px}
h2{font-size:15px;margin:0 0 3px;font-weight:700}
.sub{font-size:12.5px;color:var(--text-secondary);margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px}
.kpi{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:13px 15px}
.kpi .lab{font-size:11px;color:var(--text-secondary);font-weight:700;text-transform:uppercase;letter-spacing:.4px}
.kpi .val{font-size:26px;font-weight:800;margin-top:5px;letter-spacing:-.6px}
.kpi .note{font-size:11.5px;color:var(--muted);margin-top:2px}
.bars{display:flex;flex-direction:column;gap:9px}
.bar-row{display:grid;grid-template-columns:132px 1fr;gap:12px;align-items:center}
.bar-lab{font-size:12.5px;color:var(--text-secondary);font-weight:600;text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track{position:relative;height:24px;display:flex;align-items:center;gap:8px}
.fill{height:22px;border-radius:0 4px 4px 0;min-width:2px;transition:width .25s;position:relative}
.fill:hover{filter:brightness(1.08)}
.val{font-size:12.5px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.grp{display:flex;flex-direction:column;gap:3px}
.legend{display:flex;gap:16px;margin-bottom:14px;font-size:12.5px;flex-wrap:wrap}
.legend b{display:inline-flex;align-items:center;gap:6px;font-weight:600;color:var(--text-primary)}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.hist{display:flex;align-items:flex-end;gap:2px;height:150px;margin-top:6px}
.hcol{flex:1;background:var(--seq-450);border-radius:4px 4px 0 0;min-height:2px;position:relative}
.hcol:hover{background:var(--seq-600)}
.haxis{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);
  margin-top:7px;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:8px 9px;text-align:right;border-bottom:1px solid var(--grid)}
th{font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.3px;font-weight:700}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
tbody tr:hover{background:var(--plane)}
.tip{position:fixed;background:var(--text-primary);color:var(--surface-1);padding:7px 10px;
  border-radius:8px;font-size:12px;font-weight:600;pointer-events:none;opacity:0;transition:opacity .12s;
  z-index:99;white-space:nowrap;box-shadow:0 3px 12px rgba(0,0,0,.25)}
.nota{font-size:12px;color:var(--text-secondary);background:var(--plane);border-left:3px solid var(--warn);
  padding:9px 12px;border-radius:0 8px 8px 0;margin-top:14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
#heat{height:460px;border-radius:10px;overflow:hidden;border:1px solid var(--border);background:var(--plane)}
.heat-lab{background:transparent;border:0;box-shadow:none;font-weight:800;font-size:11px;
  color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.55);text-align:center;white-space:nowrap}
.scale{display:flex;align-items:center;gap:9px;margin:12px 0 4px;flex-wrap:wrap;font-size:12px}
.scale .steps{display:flex;border-radius:5px;overflow:hidden;border:1px solid var(--border)}
.scale .steps i{width:34px;height:13px;display:block}
.scale b{font-weight:600;color:var(--text-secondary)}
.seg2{display:inline-flex;border:1px solid var(--border);border-radius:9px;overflow:hidden}
.seg2 button{border:0;background:var(--surface-1);padding:6px 13px;font-size:12.5px;font-weight:700;
  cursor:pointer;color:var(--text-secondary)}
.seg2 button.on{background:var(--venda);color:#fff}
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:7px;margin-top:12px}
.cell{border-radius:9px;padding:10px 11px;color:#fff;min-height:64px;display:flex;
  flex-direction:column;justify-content:space-between}
.cell .cn{font-size:11.5px;font-weight:700;opacity:.95;line-height:1.2}
.cell .cv{font-size:15px;font-weight:800;font-variant-numeric:tabular-nums}
@media(max-width:820px){ .two{grid-template-columns:1fr} .bar-row{grid-template-columns:96px 1fr} }
footer{max-width:1180px;margin:0 auto;padding:0 20px 30px;font-size:12px;color:var(--muted)}
</style>
</head>
<body>
<header><div class="hrow">
  <h1>📊 Imóveis DF <small>análise exploratória</small></h1>
  <nav><a href="index.html">Mapa</a><a href="analise.html" class="on">Análise</a></nav>
</div></header>
<main id="main"></main>
<footer id="foot"></footer>
<div class="tip" id="tip"></div>
<script>
const D = __DADOS__;
const brl = n => n==null?'—':n.toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
const kbrl = n => n==null?'—': n>=1e6 ? 'R$ '+(n/1e6).toFixed(2).replace('.',',')+' mi'
                  : n>=10000 ? 'R$ '+Math.round(n/1000)+' mil' : brl(n);
const num = n => n==null?'—':n.toLocaleString('pt-BR');
const tip = document.getElementById('tip');
function bindTip(el, html){
  el.addEventListener('mousemove',e=>{
    tip.innerHTML=html; tip.style.opacity=1;
    tip.style.left=Math.min(window.innerWidth-tip.offsetWidth-10,e.clientX+14)+'px';
    tip.style.top=(e.clientY-38)+'px';
  });
  el.addEventListener('mouseleave',()=>tip.style.opacity=0);
}
function el(tag, cls, html){ const n=document.createElement(tag); if(cls)n.className=cls; if(html!=null)n.innerHTML=html; return n; }

/* ---------- barras horizontais (1 serie, sequencial) ---------- */
function barChart(rows, {fmt=kbrl, color='var(--seq-450)', tipFmt}={}){
  const max = Math.max(...rows.map(r=>r.v||0)) || 1;
  const wrap = el('div','bars');
  rows.forEach(r=>{
    const row = el('div','bar-row');
    row.appendChild(el('div','bar-lab', r.label));
    const track = el('div','track');
    const fill = el('div','fill');
    fill.style.width = ((r.v||0)/max*100)+'%';
    fill.style.background = r.color || color;
    track.appendChild(fill);
    track.appendChild(el('span','val', r.vlabel!=null?r.vlabel:fmt(r.v)));
    bindTip(fill, tipFmt? tipFmt(r) : r.label+': '+fmt(r.v));
    row.appendChild(track); wrap.appendChild(row);
  });
  return wrap;
}
/* ---------- barras agrupadas (2 series) ---------- */
function groupChart(rows, series){
  const max = Math.max(...rows.flatMap(r=>series.map(s=>r[s.key]||0))) || 1;
  const wrap = el('div','bars');
  rows.forEach(r=>{
    const row = el('div','bar-row');
    row.appendChild(el('div','bar-lab', r.label));
    const grp = el('div','grp');
    series.forEach(s=>{
      const track = el('div','track'); track.style.height='19px';
      const fill = el('div','fill'); fill.style.height='17px';
      fill.style.width=((r[s.key]||0)/max*100)+'%'; fill.style.background=s.color;
      track.appendChild(fill);
      track.appendChild(el('span','val', s.fmt(r[s.key])));
      bindTip(fill, r.label+' · '+s.name+': '+s.fmt(r[s.key])+(r[s.nkey]!=null?' ('+num(r[s.nkey])+' anúncios)':''));
      grp.appendChild(track);
    });
    row.appendChild(grp); wrap.appendChild(row);
  });
  return wrap;
}
/* ---------- histograma ---------- */
function histChart(h, fmt){
  const box = el('div');
  const bars = el('div','hist');
  h.bins.forEach(b=>{
    const c = el('div','hcol');
    c.style.height = Math.max(2,(b.n/h.max*100))+'%';
    bindTip(c, fmt(b.x0)+' – '+fmt(b.x1)+'<br>'+num(b.n)+' imóveis');
    bars.appendChild(c);
  });
  box.appendChild(bars);
  const ax = el('div','haxis');
  ax.appendChild(el('span',null,fmt(h.bins[0].x0)));
  ax.appendChild(el('span',null,fmt(h.bins[Math.floor(h.bins.length/2)].x0)));
  ax.appendChild(el('span',null,fmt(h.bins[h.bins.length-1].x1)));
  box.appendChild(ax);
  return box;
}
function section(title, sub){
  const s = el('section'); s.appendChild(el('h2',null,title));
  if(sub) s.appendChild(el('p','sub',sub));
  return s;
}
function legend(items){
  const l = el('div','legend');
  items.forEach(i=>l.appendChild(el('b',null,'<span class="sw" style="background:'+i.color+'"></span>'+i.name)));
  return l;
}

const main = document.getElementById('main');
const R = D.regioes, K = D.kpi;

/* ===== KPIs ===== */
{
  const s = section('Panorama', 'Base coletada em '+D.gerado.split('-').reverse().join('/')+
    ' · '+num(K.brutos)+' anúncios brutos, '+num(K.dups)+' duplicados fundidos pelo menor preço.');
  const g = el('div','kpis');
  [['Imóveis únicos',num(K.total),K.regioes+' regiões'],
   ['À venda',num(K.venda),(K.venda/K.total*100).toFixed(0)+'% da base'],
   ['Para alugar',num(K.aluguel),(K.aluguel/K.total*100).toFixed(0)+'% da base'],
   ['Venda mediana',kbrl(K.med_venda),'todas as regiões'],
   ['Aluguel mediano',kbrl(K.med_aluguel),'por mês'],
   ['m² (apto, venda)',brl(K.m2_venda),'mediana do m²']
  ].forEach(([l,v,n])=>{
    const k=el('div','kpi'); k.appendChild(el('div','lab',l));
    k.appendChild(el('div','val',v)); k.appendChild(el('div','note',n)); g.appendChild(k);
  });
  s.appendChild(g); main.appendChild(s);
}

/* ===== oferta por regiao ===== */
{
  const s = section('Onde está a oferta',
    'Quantidade de anúncios únicos por região, separando venda e aluguel.');
  s.appendChild(legend([{name:'À venda',color:'var(--venda)'},{name:'Para alugar',color:'var(--aluguel)'}]));
  s.appendChild(groupChart(
    R.map(r=>({label:r.label, n_venda:r.n_venda, n_aluguel:r.n_aluguel})),
    [{key:'n_venda',name:'venda',color:'var(--venda)',fmt:num},
     {key:'n_aluguel',name:'aluguel',color:'var(--aluguel)',fmt:num}]));
  s.appendChild(el('div','nota','Águas Claras concentra a maior oferta da base — é a região com mais prédios novos entre as pesquisadas. O aluguel é um mercado bem menor que a venda em todas elas.'));
  main.appendChild(s);
}

/* ===== preco mediano ===== */
{
  const two = el('div','two');
  const s1 = section('Preço de venda (mediana)','Metade dos imóveis custa menos que esse valor.');
  s1.appendChild(barChart(R.map(r=>({label:r.label,v:r.med_venda,color:'var(--venda)'})),
    {tipFmt:r=>r.label+': '+brl(r.v)}));
  const s2 = section('Aluguel mensal (mediana)','Mesma leitura, para locação.');
  s2.appendChild(barChart(R.map(r=>({label:r.label,v:r.med_aluguel,color:'var(--aluguel)'})),
    {fmt:brl, tipFmt:r=>r.label+': '+brl(r.v)+'/mês'}));
  two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
}

/* ===== R$/m2 — dois graficos: as escalas sao ordens de grandeza diferentes
       (milhares vs dezenas), entao dividir a mesma barra falsearia a leitura ===== */
{
  const nota = 'Casas ficam de fora de propósito: a área anunciada costuma incluir o lote, o que derrubaria artificialmente o m² de Jardim Botânico, Sobradinho e Grande Colorado.';
  const two = el('div','two');
  const s1 = section('Preço do m² — venda (só apartamentos)',
    'O indicador que realmente compara regiões. '+nota);
  s1.appendChild(barChart(R.map(r=>({label:r.label,v:r.m2_venda,color:'var(--venda)'})),
    {fmt:brl, tipFmt:r=>r.label+': '+brl(r.v)+' por m²'}));
  const s2 = section('Preço do m² — aluguel (só apartamentos)',
    'Quanto se paga por m² de aluguel a cada mês. Escala própria: são dezenas de reais, não milhares.');
  s2.appendChild(barChart(R.map(r=>({label:r.label,v:r.m2_aluguel,color:'var(--aluguel)'})),
    {fmt:brl, tipFmt:r=>r.label+': '+brl(r.v)+' por m²/mês'}));
  two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
}

/* ===== rentabilidade ===== */
{
  const s = section('Rentabilidade anual bruta (implícita)',
    'Aluguel mediano × 12 ÷ preço de venda mediano, por região. É uma referência de mercado, não o retorno de um imóvel específico — compara conjuntos diferentes de anúncios e ignora condomínio, IPTU e vacância.');
  const rows = R.filter(r=>r.yield!=null).sort((a,b)=>b.yield-a.yield)
    .map(r=>({label:r.label, v:r.yield, color: r.yield_confiavel?'var(--seq-450)':'var(--seq-250)',
              vlabel:r.yield.toFixed(1).replace('.',',')+'%'+(r.yield_confiavel?'':' *'),
              n:r.n_aluguel}));
  s.appendChild(barChart(rows,{tipFmt:r=>r.label+': '+r.v.toFixed(1).replace('.',',')+'% ao ano<br>base: '+num(r.n)+' anúncios de aluguel'}));
  s.appendChild(el('div','nota','* Regiões com menos de 30 anúncios de aluguel (barra clara) têm amostra pequena — trate o número como indicativo. Grande Colorado, por exemplo, tem só '+num(R.find(r=>r.key==='grande-colorado').n_aluguel)+' anúncios de locação.'));
  main.appendChild(s);
}

/* ===== mapa de calor por quadra + faixa por regiao ===== */
{
  // rampa sequencial de um hue so: claro = mais barato, escuro = mais caro
  const RAMPA = ['#cde2fb','#9ec5f4','#6da7ec','#3987e5','#256abf','#184f95','#0d366b'];
  const s = section('Mapa de calor — quanto custa cada quadra',
    'Cada bolha é uma quadra (mínimo de 3 anúncios). Quanto mais escura, mais cara. '+
    'As cores são divididas por quantis, então cada faixa tem mais ou menos o mesmo número de quadras.');

  const seg = el('div','seg2');
  [['m2','R$/m² (apartamentos)'],['med','Preço mediano de venda']].forEach(([k,nome],i)=>{
    const b=el('button',i===0?'on':null,nome); b.dataset.k=k; seg.appendChild(b);
  });
  s.appendChild(seg);
  const escala = el('div','scale');
  s.appendChild(escala);
  const box = el('div'); box.id='heat'; s.appendChild(box);
  s.appendChild(el('div','nota','Em R$/m² só entram apartamentos: em casa a área anunciada costuma incluir o lote, o que faria uma quadra de casas parecer barata sem ser. Na opção "preço mediano" entram todos os tipos — ali uma quadra de casas grandes aparece cara por ser casa, não por ser cara o m².'));
  main.appendChild(s);

  const map = L.map('heat',{scrollWheelZoom:false}).setView([-15.79,-47.89],11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom:19, attribution:'© OpenStreetMap', opacity:.55}).addTo(map);
  const camada = L.layerGroup().addTo(map);

  function quantis(vals,n){
    const v=vals.slice().sort((a,b)=>a-b), cortes=[];
    for(let i=1;i<n;i++) cortes.push(v[Math.floor(v.length*i/n)]);
    return cortes;
  }
  function desenhar(metrica){
    camada.clearLayers();
    const dados = D.quadras.filter(q=>q[metrica]!=null);
    const cortes = quantis(dados.map(q=>q[metrica]), RAMPA.length);
    const cor = v => RAMPA[cortes.filter(c=>v>=c).length];
    const fmt = v => metrica==='m2' ? brl(v)+'/m²' : kbrl(v);
    const maxN = Math.max(...dados.map(q=>q.n));
    dados.forEach(q=>{
      const raio = 7 + 13*Math.sqrt(q.n/maxN);
      const c = L.circleMarker([q.lat,q.lon],{
        radius:raio, fillColor:cor(q[metrica]), fillOpacity:.87,
        color:'#fff', weight:1.5
      });
      c.bindTooltip('<b>'+q.q+'</b> · '+(RLABEL[q.r]||'')+'<br>'+
        (q.m2!=null?'R$/m² (apto): '+brl(q.m2)+'<br>':'')+
        (q.med!=null?'Venda mediana: '+kbrl(q.med)+'<br>':'')+
        q.n+' anúncios',{sticky:true});
      camada.addLayer(c);
    });
    // legenda: faixas de valor da rampa
    escala.innerHTML='';
    escala.appendChild(el('b',null,'mais barato'));
    const steps=el('div','steps');
    RAMPA.forEach(c=>{const i=el('i'); i.style.background=c; steps.appendChild(i);});
    escala.appendChild(steps);
    escala.appendChild(el('b',null,'mais caro'));
    escala.appendChild(el('b',null,'· '+fmt(Math.min(...dados.map(q=>q[metrica])))+
      ' a '+fmt(Math.max(...dados.map(q=>q[metrica])))+' · '+dados.length+' quadras'));
    if(dados.length){
      map.fitBounds(L.latLngBounds(dados.map(q=>[q.lat,q.lon])).pad(0.06));
    }
  }
  seg.addEventListener('click',e=>{
    const b=e.target.closest('button'); if(!b)return;
    [...seg.children].forEach(c=>c.classList.toggle('on',c===b));
    desenhar(b.dataset.k);
  });
  desenhar('m2');
  setTimeout(()=>map.invalidateSize(),200);

  /* faixa por regiao (mesma rampa) */
  const s2 = section('Mapa de calor por região','Mediana do m² de apartamentos à venda em cada região.');
  const comM2 = R.filter(r=>r.m2_venda!=null).sort((a,b)=>b.m2_venda-a.m2_venda);
  const cortesR = quantis(comM2.map(r=>r.m2_venda), RAMPA.length);
  const strip = el('div','strip');
  comM2.forEach(r=>{
    const c = el('div','cell');
    c.style.background = RAMPA[cortesR.filter(v=>r.m2_venda>=v).length];
    c.appendChild(el('div','cn', r.label));
    c.appendChild(el('div','cv', brl(r.m2_venda)));
    bindTip(c, r.label+'<br>R$/m² (apto, venda): '+brl(r.m2_venda)+
      '<br>venda mediana: '+kbrl(r.med_venda)+'<br>'+num(r.n)+' anúncios');
    strip.appendChild(c);
  });
  s2.appendChild(strip);
  main.appendChild(s2);
}

/* ===== distribuicoes ===== */
{
  const two = el('div','two');
  const s1 = section('Distribuição dos preços de venda','Entre os percentis 1 e 99. Cada barra é uma faixa de preço.');
  s1.appendChild(histChart(D.hist_venda,kbrl));
  const s2 = section('Distribuição dos aluguéis','Mesma leitura, valores mensais.');
  s2.appendChild(histChart(D.hist_aluguel,kbrl));
  two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
}

/* ===== quartos x tipo ===== */
{
  const s = section('Quanto custa por quartos e tipo',
    'Preço mediano de venda, apartamento vs casa.');
  s.appendChild(legend([{name:'Apartamento',color:'var(--venda)'},{name:'Casa',color:'var(--casa)'}]));
  const rows=[1,2,3].map(b=>{
    const ap=D.quartos.find(q=>q.kind==='apartamento'&&q.b===b)||{};
    const ca=D.quartos.find(q=>q.kind==='casa'&&q.b===b)||{};
    return {label:b+' quarto'+(b>1?'s':''), ap:ap.med_venda, ca:ca.med_venda,
            n_ap:ap.n_venda, n_ca:ca.n_venda};
  });
  s.appendChild(groupChart(rows,[
    {key:'ap',name:'apartamento',color:'var(--venda)',fmt:kbrl,nkey:'n_ap'},
    {key:'ca',name:'casa',color:'var(--casa)',fmt:kbrl,nkey:'n_ca'}]));
  s.appendChild(el('div','nota','Casas de 1 e 2 quartos são poucas na base ('+num(rows[0].n_ca+rows[1].n_ca)+' à venda) e concentradas em regiões mais baratas, por isso a comparação com apartamento nesses tamanhos é menos estável que no 3 quartos.'));
  main.appendChild(s);
}

/* ===== area + composicao ===== */
{
  const two = el('div','two');
  const s1 = section('Distribuição das áreas','Área anunciada, em m² (percentis 1–99).');
  s1.appendChild(histChart(D.hist_area, v=>Math.round(v)+' m²'));
  const s2 = section('Composição da base','Como os anúncios se dividem.');
  const comp=[
    {label:'Apartamento', v:D.tipo.apartamento||0},
    {label:'Casa', v:D.tipo.casa||0},
    {label:'Outros', v:D.tipo.outro||0},
    {label:'1 quarto', v:D.quartos_dist['1']||0},
    {label:'2 quartos', v:D.quartos_dist['2']||0},
    {label:'3 quartos', v:D.quartos_dist['3']||0},
    {label:'DFImóveis', v:D.fonte.dfimoveis||0},
    {label:'Wimóveis', v:D.fonte.wimoveis||0},
  ];
  s2.appendChild(barChart(comp,{fmt:num,tipFmt:r=>r.label+': '+num(r.v)+' imóveis ('+(r.v/K.total*100).toFixed(1)+'%)'}));
  two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
}

/* ===== tabela ===== */
{
  const s = section('Tabela completa por região','Todos os números acima, para leitura direta.');
  const t = el('table');
  t.innerHTML = '<thead><tr><th>Região</th><th>Venda</th><th>Mediana</th><th>R$/m² apto</th>'+
    '<th>Aluguel</th><th>Mediana</th><th>Rentab.</th><th>Área méd.</th><th>Casas</th></tr></thead>';
  const tb = el('tbody');
  R.forEach(r=>{
    const tr=el('tr');
    tr.innerHTML = '<td>'+r.label+'</td><td>'+num(r.n_venda)+'</td><td>'+kbrl(r.med_venda)+'</td>'+
      '<td>'+(r.m2_venda?brl(r.m2_venda):'—')+'</td><td>'+num(r.n_aluguel)+'</td>'+
      '<td>'+(r.med_aluguel?brl(r.med_aluguel):'—')+'</td>'+
      '<td>'+(r.yield!=null?r.yield.toFixed(1).replace('.',',')+'%':'—')+'</td>'+
      '<td>'+(r.area?Math.round(r.area)+' m²':'—')+'</td><td>'+num(r.casas)+'</td>';
    tb.appendChild(tr);
  });
  t.appendChild(tb); s.appendChild(t); main.appendChild(s);
}

document.getElementById('foot').innerHTML =
  'Fontes: dfimoveis.com.br e wimoveis.com.br · apartamentos e casas de 1 a 3 quartos · '+
  'anúncios duplicados entre os dois portais foram fundidos mantendo o menor preço · '+
  'coordenadas fora da região e preços absurdos (erro de digitação do anunciante) foram descartados · '+
  'retrato de '+D.gerado.split('-').reverse().join('/')+'.';
</script>
</body>
</html>"""

if __name__ == "__main__":
    main()
