# -*- coding: utf-8 -*-
"""
Gera analise.html — analise exploratoria (EDA) dos imoveis coletados.

Usa a mesma limpeza do build.py (preco, geografia, outliers, endereco, dedup).
Diferente das versoes anteriores, os agregados NAO vem prontos do Python: a
pagina recebe os imoveis em formato enxuto e recalcula tudo no navegador, para
que o filtro de quartos valha para todos os graficos ao mesmo tempo.
"""
import json, os, statistics as st, datetime
from collections import defaultdict
from scrape import REGIONS
from build import (valid_price, valid_geo, drop_outliers, dedup,
                   extract_quadra, extract_bloco, snap_para_quadra)

AREA_MIN, AREA_MAX = 20, 2000        # area plausivel p/ calcular R$/m2


def carregar():
    """Mesmo pipeline do build.py — inclusive o reposicionamento pelo endereco,
    para que os centros de quadra do mapa de calor batam com os do mapa."""
    raw = json.load(open("raw_listings.json", encoding="utf-8"))
    d = [x for x in raw if valid_price(x) and valid_geo(x)]
    d, _ = drop_outliers(d)
    for x in d:
        x["quadra"] = extract_quadra(x)
        x["bloco"] = extract_bloco(x)
    snap_para_quadra(d)
    d, dups = dedup(d)
    return raw, d, dups


def main():
    raw, d, dups = carregar()

    ordem = [r["key"] for r in REGIONS]
    idx = {k: i for i, k in enumerate(ordem)}
    kmap = {"apartamento": "a", "casa": "c"}

    itens = []
    for x in d:
        rec = {
            "r": idx[x["region"]],
            "o": "v" if x["operation"] == "venda" else "a",
            "k": kmap.get(x.get("kind"), "o"),
            "b": int(x["bedrooms"]),
            "p": round(x["price"]),
            "s": "d" if x["source"] == "dfimoveis" else "w",
        }
        if x.get("area") and AREA_MIN < x["area"] < AREA_MAX:
            rec["ar"] = round(x["area"])
        if x.get("quadra"):
            rec["q"] = x["quadra"]
        itens.append(rec)

    # centro de cada quadra (fixo): o mapa de calor so recalcula os VALORES ao
    # filtrar, nunca a posicao — assim as bolhas nao dancam pelo mapa
    porq = defaultdict(list)
    for x in d:
        if x.get("quadra") and any(c.isdigit() for c in x["quadra"]):
            porq[x["quadra"]].append(x)
    centros = {q: [round(st.median([y["lat"] for y in g]), 5),
                   round(st.median([y["lon"] for y in g]), 5),
                   idx[g[0]["region"]]]
               for q, g in porq.items() if len(g) >= 3}

    coletado = None
    if os.path.exists("raw_meta.json"):
        try:
            coletado = json.load(open("raw_meta.json", encoding="utf-8")).get("coletado_em")
        except Exception:
            coletado = None
    if not coletado:
        coletado = datetime.date.fromtimestamp(
            os.path.getmtime("raw_listings.json")).isoformat()

    dados = {
        "gerado": coletado,
        "brutos": len(raw),
        "dups": dups,
        "regioes": [{"k": r["key"], "n": r["label"]} for r in REGIONS],
        "centros": centros,
        "itens": itens,
    }

    html = TEMPLATE.replace("__DADOS__", json.dumps(dados, ensure_ascii=False,
                                                    separators=(",", ":")))
    open("analise.html", "w", encoding="utf-8").write(html)
    print(f"-> analise.html gerado ({os.path.getsize('analise.html')/1024:.0f} KB)")
    print(f"   {len(itens)} imoveis | {sum(1 for x in itens if x['o']=='v')} venda "
          f"| {sum(1 for x in itens if x['o']=='a')} aluguel | {len(centros)} quadras")


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
  --seq-450:#2a78d6; --seq-250:#86b6ef; --seq-600:#184f95;
  --warn:#fab219;
}
@media (prefers-color-scheme: dark){
  :root:where(:not([data-theme="light"])){
    color-scheme: dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --text-primary:#fff; --text-secondary:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
    --venda:#3987e5; --aluguel:#199e70; --casa:#d95926;
    --seq-450:#3987e5; --seq-250:#1c5cab; --seq-600:#86b6ef;
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface-1:#1a1a19; --plane:#0d0d0d;
  --text-primary:#fff; --text-secondary:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --venda:#3987e5; --aluguel:#199e70; --casa:#d95926;
  --seq-450:#3987e5; --seq-250:#1c5cab; --seq-600:#86b6ef;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--text-primary);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
header{background:var(--surface-1);border-bottom:1px solid var(--border);padding:11px 20px;
  position:sticky;top:0;z-index:1200}
.hrow{display:flex;align-items:center;gap:14px;flex-wrap:wrap;max-width:1180px;margin:0 auto}
h1{font-size:17px;margin:0;font-weight:700;letter-spacing:-.2px}
h1 small{font-weight:500;color:var(--text-secondary);font-size:12px;margin-left:6px}
nav{display:inline-flex;border:1px solid var(--border);border-radius:9px;overflow:hidden}
nav a{padding:7px 15px;font-size:13px;font-weight:700;text-decoration:none;color:var(--text-secondary);background:var(--surface-1)}
nav a.on{background:var(--venda);color:#fff}
.filtros{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-left:auto}
.flab{font-size:11px;font-weight:700;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.4px}
.chips{display:inline-flex;gap:5px}
.chip{border:1px solid var(--border);background:var(--surface-1);border-radius:999px;
  padding:5px 13px;font-size:12.5px;font-weight:700;cursor:pointer;color:var(--text-secondary);user-select:none}
.chip.on{background:var(--text-primary);color:var(--surface-1);border-color:var(--text-primary)}
#total{font-size:12.5px;font-weight:700;color:var(--text-primary)}
main{max-width:1180px;margin:0 auto;padding:20px}
section{background:var(--surface-1);border:1px solid var(--border);border-radius:14px;
  padding:18px 20px 20px;margin-bottom:16px}
h2{font-size:15px;margin:0 0 3px;font-weight:700}
.sub{font-size:12.5px;color:var(--text-secondary);margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px}
.kpi{border:1px solid var(--border);border-radius:12px;padding:13px 15px}
.kpi .lab{font-size:11px;color:var(--text-secondary);font-weight:700;text-transform:uppercase;letter-spacing:.4px}
.kpi .val{font-size:26px;font-weight:800;margin-top:5px;letter-spacing:-.6px}
.kpi .note{font-size:11.5px;color:var(--muted);margin-top:2px}
.bars{display:flex;flex-direction:column;gap:9px}
.bar-row{display:grid;grid-template-columns:132px 1fr;gap:12px;align-items:center}
.bar-lab{font-size:12.5px;color:var(--text-secondary);font-weight:600;text-align:right;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track{position:relative;height:24px;display:flex;align-items:center;gap:8px}
.fill{height:22px;border-radius:0 4px 4px 0;min-width:2px;transition:width .25s}
.fill:hover{filter:brightness(1.08)}
.val{font-size:12.5px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.grp{display:flex;flex-direction:column;gap:3px}
.legend{display:flex;gap:16px;margin-bottom:14px;font-size:12.5px;flex-wrap:wrap}
.legend b{display:inline-flex;align-items:center;gap:6px;font-weight:600;color:var(--text-primary)}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block}
.hist{display:flex;align-items:flex-end;gap:2px;height:150px;margin-top:6px}
.hcol{flex:1;background:var(--seq-450);border-radius:4px 4px 0 0;min-height:2px}
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
  z-index:9999;white-space:nowrap;box-shadow:0 3px 12px rgba(0,0,0,.25)}
.nota{font-size:12px;color:var(--text-secondary);background:var(--plane);border-left:3px solid var(--warn);
  padding:9px 12px;border-radius:0 8px 8px 0;margin-top:14px}
.vazio{font-size:13px;color:var(--muted);padding:10px 0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
#heat{height:460px;border-radius:10px;overflow:hidden;border:1px solid var(--border);background:var(--plane)}
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
@media(max-width:900px){ .two{grid-template-columns:1fr} h1 small{display:none} }
</style>
</head>
<body>
<header><div class="hrow">
  <h1>📊 Imóveis DF <small>análise exploratória</small></h1>
  <nav><a href="index.html">Mapa</a><a href="analise.html" class="on">Análise</a><a href="custo_beneficio.html">Custo-benefício</a></nav>
  <div class="filtros">
    <span class="flab">Quartos</span>
    <div class="chips" id="bedChips">
      <span class="chip on" data-b="1">1q</span>
      <span class="chip on" data-b="2">2q</span>
      <span class="chip on" data-b="3">3q</span>
    </div>
    <span class="flab">Tipo</span>
    <div class="chips" id="kindChips">
      <span class="chip on" data-k="a">Apto</span>
      <span class="chip on" data-k="c">Casa</span>
    </div>
    <span id="total"></span>
  </div>
</div></header>
<main id="main"></main>
<footer id="foot" style="max-width:1180px;margin:0 auto;padding:0 20px 30px;font-size:12px;color:var(--muted)"></footer>
<div class="tip" id="tip"></div>
<script>
const D = __DADOS__;
const REG = D.regioes, RN = REG.map(r=>r.n);
const brl = n => n==null?'—':n.toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
const kbrl = n => n==null?'—': n>=1e6 ? 'R$ '+(n/1e6).toLocaleString('pt-BR',{maximumFractionDigits:2})+' mi'
                  : n>=10000 ? 'R$ '+Math.round(n/1000)+' mil' : brl(n);
const num = n => n==null?'—':n.toLocaleString('pt-BR');
const pct = n => n.toFixed(1).replace('.',',')+'%';
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

/* ---------- estatistica ---------- */
function mediana(v){ if(!v.length) return null; const s=v.slice().sort((a,b)=>a-b);
  const m=s.length>>1; return s.length%2 ? s[m] : (s[m-1]+s[m])/2; }
function quantis(v,n){ const s=v.slice().sort((a,b)=>a-b), c=[];
  for(let i=1;i<n;i++) c.push(s[Math.floor(s.length*i/n)]); return c; }
function hist(v,nb){
  nb = nb||22;
  if(!v.length) return {bins:[],max:0};
  const s=v.slice().sort((a,b)=>a-b);
  const lo=s[Math.floor(s.length*.01)], hi0=s[Math.floor(s.length*.99)];
  const hi = hi0>lo ? hi0 : lo+1, w=(hi-lo)/nb, c=new Array(nb).fill(0);
  for(const x of s){ if(x<lo||x>hi) continue; c[Math.min(nb-1,Math.floor((x-lo)/w))]++; }
  return {bins:c.map((n,i)=>({x0:lo+i*w,x1:lo+(i+1)*w,n})), max:Math.max(...c)};
}

/* ---------- graficos ---------- */
function barChart(rows,{fmt=kbrl,color='var(--seq-450)',tipFmt}={}){
  const max=Math.max(...rows.map(r=>r.v||0))||1, wrap=el('div','bars');
  rows.forEach(r=>{
    const row=el('div','bar-row');
    row.appendChild(el('div','bar-lab',r.label));
    const track=el('div','track'), fill=el('div','fill');
    fill.style.width=((r.v||0)/max*100)+'%'; fill.style.background=r.color||color;
    track.appendChild(fill);
    track.appendChild(el('span','val', r.vlabel!=null?r.vlabel:fmt(r.v)));
    bindTip(fill, tipFmt?tipFmt(r):r.label+': '+fmt(r.v));
    row.appendChild(track); wrap.appendChild(row);
  });
  return wrap;
}
function groupChart(rows,series){
  const max=Math.max(...rows.flatMap(r=>series.map(s=>r[s.key]||0)))||1, wrap=el('div','bars');
  rows.forEach(r=>{
    const row=el('div','bar-row');
    row.appendChild(el('div','bar-lab',r.label));
    const grp=el('div','grp');
    series.forEach(s=>{
      const track=el('div','track'); track.style.height='19px';
      const fill=el('div','fill'); fill.style.height='17px';
      fill.style.width=((r[s.key]||0)/max*100)+'%'; fill.style.background=s.color;
      track.appendChild(fill);
      track.appendChild(el('span','val',s.fmt(r[s.key])));
      bindTip(fill, r.label+' · '+s.name+': '+s.fmt(r[s.key])+
        (r[s.nkey]!=null?' ('+num(r[s.nkey])+' anúncios)':''));
      grp.appendChild(track);
    });
    row.appendChild(grp); wrap.appendChild(row);
  });
  return wrap;
}
function histChart(h,fmt){
  const box=el('div');
  if(!h.bins.length){ box.appendChild(el('div','vazio','Sem dados para este filtro.')); return box; }
  const bars=el('div','hist');
  h.bins.forEach(b=>{
    const c=el('div','hcol'); c.style.height=Math.max(2,b.n/h.max*100)+'%';
    bindTip(c, fmt(b.x0)+' – '+fmt(b.x1)+'<br>'+num(b.n)+' imóveis');
    bars.appendChild(c);
  });
  box.appendChild(bars);
  const ax=el('div','haxis');
  ax.appendChild(el('span',null,fmt(h.bins[0].x0)));
  ax.appendChild(el('span',null,fmt(h.bins[Math.floor(h.bins.length/2)].x0)));
  ax.appendChild(el('span',null,fmt(h.bins[h.bins.length-1].x1)));
  box.appendChild(ax);
  return box;
}
function section(title,sub){
  const s=el('section'); s.appendChild(el('h2',null,title));
  if(sub) s.appendChild(el('p','sub',sub));
  return s;
}
function legend(items){
  const l=el('div','legend');
  items.forEach(i=>l.appendChild(el('b',null,'<span class="sw" style="background:'+i.color+'"></span>'+i.name)));
  return l;
}

/* ---------- agregacao (recalculada a cada filtro) ---------- */
const estado = { beds:new Set([1,2,3]), kinds:new Set(['a','c','o']) };
function passa(x){ return estado.beds.has(x.b) && estado.kinds.has(x.k); }

function agregar(){
  const d = D.itens.filter(passa);
  const venda = d.filter(x=>x.o==='v'), aluguel = d.filter(x=>x.o==='a');
  const m2 = (arr,so) => arr.filter(x=>x.ar && (!so || x.k===so)).map(x=>x.p/x.ar);

  const regioes = REG.map((r,i)=>{
    const v=venda.filter(x=>x.r===i), a=aluguel.filter(x=>x.r===i);
    const mv=mediana(v.map(x=>x.p)), ma=mediana(a.map(x=>x.p));
    return { label:r.n, key:r.k,
      n:v.length+a.length, n_venda:v.length, n_aluguel:a.length,
      med_venda:mv, med_aluguel:ma,
      m2_venda:mediana(m2(v,'a')), m2_aluguel:mediana(m2(a,'a')),
      area:mediana(v.filter(x=>x.ar).map(x=>x.ar)),
      rent:(mv&&ma)? ma*12/mv*100 : null,
      confia:a.length>=30,
      casas:(v.concat(a)).filter(x=>x.k==='c').length };
  }).filter(r=>r.n>0);

  // quadras: posicao fixa, valores recalculados
  const porq = {};
  for(const x of venda){ if(x.q&&D.centros[x.q]){ (porq[x.q]=porq[x.q]||[]).push(x); } }
  const quadras = Object.entries(porq).filter(([q,g])=>g.length>=3).map(([q,g])=>{
    const c=D.centros[q], ap=g.filter(x=>x.ar&&x.k==='a').map(x=>x.p/x.ar);
    return { q, lat:c[0], lon:c[1], r:c[2], n:g.length,
             m2:mediana(ap), med:mediana(g.map(x=>x.p)) };
  });

  return { d, venda, aluguel, regioes, quadras,
    kpi:{ total:d.length, venda:venda.length, aluguel:aluguel.length,
          med_venda:mediana(venda.map(x=>x.p)), med_aluguel:mediana(aluguel.map(x=>x.p)),
          m2_venda:mediana(m2(venda,'a')) },
    hv:hist(venda.map(x=>x.p)), ha:hist(aluguel.map(x=>x.p)),
    har:hist(d.filter(x=>x.ar).map(x=>x.ar)),
    quartos:[1,2,3].map(b=>({
      b, ap:mediana(venda.filter(x=>x.k==='a'&&x.b===b).map(x=>x.p)),
      ca:mediana(venda.filter(x=>x.k==='c'&&x.b===b).map(x=>x.p)),
      n_ap:venda.filter(x=>x.k==='a'&&x.b===b).length,
      n_ca:venda.filter(x=>x.k==='c'&&x.b===b).length })),
    comp:[
      {label:'Apartamento',v:d.filter(x=>x.k==='a').length},
      {label:'Casa',v:d.filter(x=>x.k==='c').length},
      {label:'1 quarto',v:d.filter(x=>x.b===1).length},
      {label:'2 quartos',v:d.filter(x=>x.b===2).length},
      {label:'3 quartos',v:d.filter(x=>x.b===3).length},
      {label:'DFImóveis',v:d.filter(x=>x.s==='d').length},
      {label:'Wimóveis',v:d.filter(x=>x.s==='w').length},
    ].filter(c=>c.v>0) };
}

/* ---------- render ---------- */
const RAMPA = ['#cde2fb','#9ec5f4','#6da7ec','#3987e5','#256abf','#184f95','#0d366b'];
const main = document.getElementById('main');
let heatMap=null, heatCamada=null, heatLimites=null, heatMetrica='m2', A=null;

function desenharHeat(){
  if(!heatMap) return;
  heatCamada.clearLayers();
  const dados = A.quadras.filter(q=>q[heatMetrica]!=null);
  const escala = document.getElementById('escala');
  escala.innerHTML='';
  if(!dados.length){ escala.appendChild(el('b',null,'Sem quadras suficientes neste filtro.')); return; }
  const cortes = quantis(dados.map(q=>q[heatMetrica]), RAMPA.length);
  const cor = v => RAMPA[cortes.filter(c=>v>=c).length];
  const fmt = v => heatMetrica==='m2' ? brl(v)+'/m²' : kbrl(v);
  const maxN = Math.max(...dados.map(q=>q.n));
  dados.forEach(q=>{
    const c = L.circleMarker([q.lat,q.lon],{
      radius: 7+13*Math.sqrt(q.n/maxN), fillColor:cor(q[heatMetrica]),
      fillOpacity:.87, color:'#fff', weight:1.5});
    c.bindTooltip('<b>'+q.q+'</b> · '+RN[q.r]+'<br>'+
      (q.m2!=null?'R$/m² (apto): '+brl(q.m2)+'<br>':'')+
      (q.med!=null?'Venda mediana: '+kbrl(q.med)+'<br>':'')+
      q.n+' anúncios à venda',{sticky:true});
    heatCamada.addLayer(c);
  });
  escala.appendChild(el('b',null,'mais barato'));
  const steps=el('div','steps');
  RAMPA.forEach(c=>{const i=el('i'); i.style.background=c; steps.appendChild(i);});
  escala.appendChild(steps);
  escala.appendChild(el('b',null,'mais caro'));
  escala.appendChild(el('b',null,'· '+fmt(Math.min(...dados.map(q=>q[heatMetrica])))+' a '+
    fmt(Math.max(...dados.map(q=>q[heatMetrica])))+' · '+dados.length+' quadras'));
  heatLimites = L.latLngBounds(dados.map(q=>[q.lat,q.lon])).pad(0.06);
  heatMap.fitBounds(heatLimites);
}

function render(){
  A = agregar();
  const R = A.regioes, K = A.kpi;
  main.innerHTML='';
  document.getElementById('total').textContent = num(K.total)+' imóveis';

  if(!K.total){
    main.appendChild(section('Nenhum imóvel neste filtro','Ligue ao menos um tipo e uma opção de quartos.'));
    return;
  }

  /* panorama */
  {
    const s = section('Panorama','Base coletada em '+D.gerado.split('-').reverse().join('/')+
      ' · '+num(D.brutos)+' anúncios brutos, '+num(D.dups)+' duplicados fundidos pelo menor preço.');
    const g = el('div','kpis');
    [['Imóveis no filtro',num(K.total),R.length+' regiões'],
     ['À venda',num(K.venda),pct(K.venda/K.total*100)+' do filtro'],
     ['Para alugar',num(K.aluguel),pct(K.aluguel/K.total*100)+' do filtro'],
     ['Venda mediana',kbrl(K.med_venda),'todas as regiões'],
     ['Aluguel mediano',kbrl(K.med_aluguel),'por mês'],
     ['m² (apto, venda)',brl(K.m2_venda),'mediana do m²']
    ].forEach(([l,v,n])=>{
      const k=el('div','kpi'); k.appendChild(el('div','lab',l));
      k.appendChild(el('div','val',v)); k.appendChild(el('div','note',n)); g.appendChild(k);
    });
    s.appendChild(g); main.appendChild(s);
  }

  /* oferta */
  {
    const s = section('Onde está a oferta','Anúncios únicos por região, separando venda e aluguel.');
    s.appendChild(legend([{name:'À venda',color:'var(--venda)'},{name:'Para alugar',color:'var(--aluguel)'}]));
    s.appendChild(groupChart(R.map(r=>({label:r.label,n_venda:r.n_venda,n_aluguel:r.n_aluguel})),
      [{key:'n_venda',name:'venda',color:'var(--venda)',fmt:num},
       {key:'n_aluguel',name:'aluguel',color:'var(--aluguel)',fmt:num}]));
    main.appendChild(s);
  }

  /* precos medianos */
  {
    const two=el('div','two');
    const s1=section('Preço de venda (mediana)','Metade dos imóveis custa menos que esse valor.');
    s1.appendChild(barChart(R.map(r=>({label:r.label,v:r.med_venda,color:'var(--venda)'})),
      {tipFmt:r=>r.label+': '+brl(r.v)}));
    const s2=section('Aluguel mensal (mediana)','Mesma leitura, para locação.');
    s2.appendChild(barChart(R.map(r=>({label:r.label,v:r.med_aluguel,color:'var(--aluguel)'})),
      {fmt:brl,tipFmt:r=>r.label+': '+brl(r.v)+'/mês'}));
    two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
  }

  /* R$/m2 — escalas separadas de proposito */
  {
    const nota='Casas ficam de fora: a área anunciada costuma incluir o lote, o que derrubaria artificialmente o m² de Jardim Botânico, Sobradinho e dos lagos.';
    const two=el('div','two');
    const s1=section('Preço do m² — venda (só apartamentos)','O indicador que realmente compara regiões. '+nota);
    s1.appendChild(barChart(R.map(r=>({label:r.label,v:r.m2_venda,color:'var(--venda)'})),
      {fmt:brl,tipFmt:r=>r.label+': '+brl(r.v)+' por m²'}));
    const s2=section('Preço do m² — aluguel (só apartamentos)','Escala própria: são dezenas de reais, não milhares.');
    s2.appendChild(barChart(R.map(r=>({label:r.label,v:r.m2_aluguel,color:'var(--aluguel)'})),
      {fmt:brl,tipFmt:r=>r.label+': '+brl(r.v)+' por m²/mês'}));
    two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
  }

  /* rentabilidade */
  {
    const s=section('Rentabilidade anual bruta (implícita)',
      'Aluguel mediano × 12 ÷ preço de venda mediano. É referência de mercado, não o retorno de um imóvel específico — compara conjuntos diferentes de anúncios e ignora condomínio, IPTU e vacância.');
    const rows=R.filter(r=>r.rent!=null).sort((a,b)=>b.rent-a.rent).map(r=>({
      label:r.label, v:r.rent, color:r.confia?'var(--seq-450)':'var(--seq-250)',
      vlabel:pct(r.rent)+(r.confia?'':' *'), n:r.n_aluguel}));
    if(rows.length){
      s.appendChild(barChart(rows,{tipFmt:r=>r.label+': '+pct(r.v)+' ao ano<br>base: '+num(r.n)+' anúncios de aluguel'}));
      s.appendChild(el('div','nota','* Barra clara = menos de 30 anúncios de aluguel no filtro atual: amostra pequena, trate como indicativo.'));
    } else s.appendChild(el('div','vazio','Sem venda e aluguel simultâneos para calcular.'));
    main.appendChild(s);
  }

  /* mapa de calor */
  {
    const s=section('Mapa de calor — quanto custa cada quadra',
      'Cada bolha é uma quadra com ao menos 3 anúncios à venda no filtro. Quanto mais escura, mais cara. As cores são divididas por quantis, então cada faixa tem mais ou menos o mesmo número de quadras.');
    const seg=el('div','seg2');
    [['m2','R$/m² (apartamentos)'],['med','Preço mediano de venda']].forEach(([k,nome])=>{
      const b=el('button',k===heatMetrica?'on':null,nome); b.dataset.k=k; seg.appendChild(b);
    });
    seg.addEventListener('click',e=>{
      const b=e.target.closest('button'); if(!b)return;
      [...seg.children].forEach(c=>c.classList.toggle('on',c===b));
      heatMetrica=b.dataset.k; desenharHeat();
    });
    s.appendChild(seg);
    const escala=el('div','scale'); escala.id='escala'; s.appendChild(escala);
    const box=el('div'); box.id='heat'; s.appendChild(box);
    s.appendChild(el('div','nota','Em R$/m² só entram apartamentos. Na opção "preço mediano" entram todos os tipos — ali uma quadra de casas grandes aparece cara por ser casa, não por ser caro o m².'));
    main.appendChild(s);

    heatMap = L.map(box,{scrollWheelZoom:false}).setView([-15.79,-47.89],10);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {maxZoom:19, attribution:'© OpenStreetMap', opacity:.55}).addTo(heatMap);
    heatCamada = L.layerGroup().addTo(heatMap);
    desenharHeat();
    // o container nasce sem tamanho util; sem reavaliar, o Leaflet enquadra o mundo
    const reajustar=()=>{ heatMap.invalidateSize(); if(heatLimites) heatMap.fitBounds(heatLimites); };
    setTimeout(reajustar,300);
    if('IntersectionObserver' in window){
      const io=new IntersectionObserver(es=>{ if(es.some(e=>e.isIntersecting)){ reajustar(); io.disconnect(); } },{threshold:.15});
      io.observe(box);
    }
    window.addEventListener('resize',reajustar);

    /* faixa por regiao */
    const s2=section('Mapa de calor por região','Mediana do m² de apartamentos à venda em cada região.');
    const comM2=R.filter(r=>r.m2_venda!=null).sort((a,b)=>b.m2_venda-a.m2_venda);
    if(comM2.length){
      const cortesR=quantis(comM2.map(r=>r.m2_venda),RAMPA.length);
      const strip=el('div','strip');
      comM2.forEach(r=>{
        const c=el('div','cell');
        c.style.background=RAMPA[cortesR.filter(v=>r.m2_venda>=v).length];
        c.appendChild(el('div','cn',r.label));
        c.appendChild(el('div','cv',brl(r.m2_venda)));
        bindTip(c, r.label+'<br>R$/m² (apto, venda): '+brl(r.m2_venda)+
          '<br>venda mediana: '+kbrl(r.med_venda)+'<br>'+num(r.n)+' anúncios');
        strip.appendChild(c);
      });
      s2.appendChild(strip);
    } else s2.appendChild(el('div','vazio','Sem apartamentos à venda neste filtro.'));
    main.appendChild(s2);
  }

  /* distribuicoes */
  {
    const two=el('div','two');
    const s1=section('Distribuição dos preços de venda','Entre os percentis 1 e 99. Cada barra é uma faixa de preço.');
    s1.appendChild(histChart(A.hv,kbrl));
    const s2=section('Distribuição dos aluguéis','Mesma leitura, valores mensais.');
    s2.appendChild(histChart(A.ha,kbrl));
    two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
  }

  /* quartos x tipo */
  {
    const s=section('Quanto custa por quartos e tipo','Preço mediano de venda, apartamento vs casa.');
    s.appendChild(legend([{name:'Apartamento',color:'var(--venda)'},{name:'Casa',color:'var(--casa)'}]));
    const rows=A.quartos.filter(q=>estado.beds.has(q.b)).map(q=>({
      label:q.b+' quarto'+(q.b>1?'s':''), ap:q.ap, ca:q.ca, n_ap:q.n_ap, n_ca:q.n_ca}));
    s.appendChild(groupChart(rows,[
      {key:'ap',name:'apartamento',color:'var(--venda)',fmt:kbrl,nkey:'n_ap'},
      {key:'ca',name:'casa',color:'var(--casa)',fmt:kbrl,nkey:'n_ca'}]));
    main.appendChild(s);
  }

  /* area + composicao */
  {
    const two=el('div','two');
    const s1=section('Distribuição das áreas','Área anunciada, em m² (percentis 1–99).');
    s1.appendChild(histChart(A.har, v=>Math.round(v)+' m²'));
    const s2=section('Composição da base','Como os anúncios do filtro se dividem.');
    s2.appendChild(barChart(A.comp,{fmt:num,
      tipFmt:r=>r.label+': '+num(r.v)+' imóveis ('+pct(r.v/K.total*100)+')'}));
    two.appendChild(s1); two.appendChild(s2); main.appendChild(two);
  }

  /* tabela */
  {
    const s=section('Tabela completa por região','Todos os números acima, para leitura direta.');
    const t=el('table');
    t.innerHTML='<thead><tr><th>Região</th><th>Venda</th><th>Mediana</th><th>R$/m² apto</th>'+
      '<th>Aluguel</th><th>Mediana</th><th>Rentab.</th><th>Área méd.</th><th>Casas</th></tr></thead>';
    const tb=el('tbody');
    R.forEach(r=>{
      const tr=el('tr');
      tr.innerHTML='<td>'+r.label+'</td><td>'+num(r.n_venda)+'</td><td>'+kbrl(r.med_venda)+'</td>'+
        '<td>'+(r.m2_venda?brl(r.m2_venda):'—')+'</td><td>'+num(r.n_aluguel)+'</td>'+
        '<td>'+(r.med_aluguel?brl(r.med_aluguel):'—')+'</td>'+
        '<td>'+(r.rent!=null?pct(r.rent):'—')+'</td>'+
        '<td>'+(r.area?Math.round(r.area)+' m²':'—')+'</td><td>'+num(r.casas)+'</td>';
      tb.appendChild(tr);
    });
    t.appendChild(tb); s.appendChild(t); main.appendChild(s);
  }
}

/* ---------- filtros ---------- */
function ligarChips(id, chave, valor){
  document.getElementById(id).addEventListener('click',e=>{
    const c=e.target.closest('.chip'); if(!c)return;
    const v=valor(c), set=estado[chave];
    if(set.has(v) && set.size>1){ set.delete(v); c.classList.remove('on'); }
    else { set.add(v); c.classList.add('on'); }
    if(chave==='kinds'){ set.has('a') ? set.add('o') : set.delete('o'); }  // "outros" acompanha apto
    render();
  });
}
ligarChips('bedChips','beds', c=>+c.dataset.b);
ligarChips('kindChips','kinds', c=>c.dataset.k);

document.getElementById('foot').innerHTML =
  'Fontes: dfimoveis.com.br e wimoveis.com.br · apartamentos e casas de 1 a 3 quartos · '+
  'anúncios duplicados entre os dois portais foram fundidos mantendo o menor preço · '+
  'coordenadas fora da região e preços absurdos (erro de digitação do anunciante) foram descartados · '+
  'retrato de '+D.gerado.split('-').reverse().join('/')+'.';

render();
</script>
</body>
</html>"""

if __name__ == "__main__":
    main()
