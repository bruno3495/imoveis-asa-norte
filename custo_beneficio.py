# -*- coding: utf-8 -*-
"""
Gera custo_beneficio.html — melhores custo-beneficio de ALUGUEL, associando
preco, tamanho do imovel e localizacao.

Como o ranking e montado (e por que assim):

1. So APARTAMENTOS. Em casa a area anunciada costuma incluir o lote, entao o
   R$/m2 de uma casa nao se compara com o de um apartamento nem com o de outra casa.
2. Area precisa ser plausivel para o numero de quartos (ha "3 quartos de 9.768 m2"
   na base, que e area do condominio inteiro). Os limites saem do percentil 99 real.
3. O indice compara cada anuncio com a MEDIANA DE R$/m2 DA PROPRIA REGIAO. Sem
   isso o ranking viraria so a lista das regioes baratas — Taguatinga ganharia de
   todo mundo e a pergunta "onde vale a pena na Asa Norte?" ficaria sem resposta.
4. O condominio entra como filtro de sanidade: quando ele e informado (so 33% dos
   anuncios) e faz o custo total por m2 passar da mediana da regiao, a pechincha
   e falsa e o anuncio sai do ranking.

O resultado sao duas leituras que se completam: o melhor negocio DENTRO de cada
regiao, e o custo absoluto do m2 ENTRE regioes.
"""
import json, statistics as st, datetime
from collections import defaultdict
from build import (valid_price, valid_geo, drop_outliers, dedup,
                   extract_quadra, extract_bloco, snap_para_quadra)
from scrape import REGIONS

LABEL = {r["key"]: r["label"] for r in REGIONS}

# ---------------------------------------------------------------------------
# Curadoria visual: a foto de capa de cada um dos melhores colocados foi aberta
# e olhada. E o passo que o numero sozinho nao da — "barato por m2" costuma ter
# um motivo, e varias vezes o motivo aparece na foto (unidade de subsolo, predio
# comercial, foto que mostra so a vista para esconder o interior).
#   ok     = interior em bom estado, pronto p/ morar
#   simples= modesto mas limpo e funcional
#   fachada= a foto so mostra o predio, nao da p/ julgar o imovel
#   alerta = a foto revela um problema que o preco escondia
# ---------------------------------------------------------------------------
AVALIACAO = {
 "https://www.wimoveis.com.br/propriedades/apartamento-para-alugar-na-asa-norte-em-brasilia-df-3043394154.html":
   ("ok", "Sala ampla e clara, porcelanato novo, luz embutida e janelões com vista verde. Reformado."),
 "https://www.wimoveis.com.br/propriedades/kitnet-mobiliada-com-garagem-na-asa-norte-em-brasilia-3045179286.html":
   ("ok", "Mobiliada e pronta para morar: estante, sofá, mesa e cozinha com bancada de granito."),
 "https://www.wimoveis.com.br/propriedades/sgan-912-ed.-master-place-otima-iluminacao-natural-3016702432.html":
   ("ok", "Compacto mas bem conservado: armários, cozinha equipada e boa luz natural."),
 "https://www.wimoveis.com.br/propriedades/res-spot-aguas-claras-mobiliado-nao-exige-fiador-3042851265.html":
   ("ok", "Torre moderna com sacadas de vidro e paisagismo cuidado. Mobiliado e sem fiador."),
 "https://www.wimoveis.com.br/propriedades/sqnw-107-02-quartos-com-armarios-com-02vg.-3041221064.html":
   ("ok", "Prédios novos do Noroeste, bem conservados. O m² mais caro do DF, mas abaixo da média local."),
 "https://www.wimoveis.com.br/propriedades/apartamento-2-andar-com-01-quarto-eqnl-21-23.-2976212265.html":
   ("simples", "Interior vazio e limpo, piso cerâmico e boa luz. 80 m² por esse valor é muito espaço."),
 "https://www.wimoveis.com.br/propriedades/apartamento-de-1-quarto-qnm-40-conjunto-a2-3045648297.html":
   ("simples", "Cozinha com acabamento novo e sacada. Modesto, mas funcional — e é o aluguel mais barato da lista."),
 "https://www.wimoveis.com.br/propriedades/apartamento-de-1-quarto-asa-norte-714-15-3043643317.html":
   ("simples", "Vazio, acabamento antigo e porta gradeada. Básico, mas limpo — e raro por esse preço na Asa Norte."),
 "https://www.wimoveis.com.br/propriedades/clrn-716-subsolo-3023744604.html":
   ("alerta", "O título diz SUBSOLO e a foto mostra a fachada comercial da rua, com banco no térreo. Aí está o desconto."),
 "https://www.dfimoveis.com.br/imovel/apartamento-2-quartos-aluguel-areal-aguas-claras-df-qs-7-rua-800-1408344":
   ("alerta", "Foto mostra prédio comercial com placa de aluguel e garagem, em rua sem asfalto. O título ainda diz Taguatinga Sul."),
 "https://www.dfimoveis.com.br/imovel/apartamento-2-quartos-aluguel-ade-aguas-claras-df-ade-conjunto-20-1359560":
   ("alerta", "Prédio de esquina com lojas de porta de aço no térreo. ADE é área de desenvolvimento econômico, zona comercial."),
 "https://www.dfimoveis.com.br/imovel/apartamento-1-quarto-aluguel-asa-norte-brasilia-df-scrn-716-bloco-h-1354668":
   ("alerta", "Sobreloja em bloco comercial (LJ 40), com desgaste aparente na fachada. Não é apartamento de superquadra."),
 "https://www.wimoveis.com.br/propriedades/kitnet-de-canto-com-garagem-e-vista-para-a-parque-da-3046390341.html":
   ("alerta", "A capa mostra só a vista de árvores e estacionamento, nada do interior."),
 "https://www.wimoveis.com.br/propriedades/perto-de-tudo-3046210204.html":
   ("fachada", "Só o jardim da superquadra, arborizado e agradável — mas nada do apartamento. Condomínio alto (R$ 1.289)."),
 "https://www.wimoveis.com.br/propriedades/sqn-313-bloco-g-locacao-apartamento-5-andar-03-2939674837.html":
   ("fachada", "Só o bloco por fora, bem conservado. O interior não foi mostrado."),
 "https://www.wimoveis.com.br/propriedades/duplex-reformado-para-locacao-3042093676.html":
   ("fachada", "Anúncio diz duplex reformado, mas a capa mostra só a torre. Confirme o estado na visita."),
}
SELO = {"ok": ("✓ bom estado", "#0ca30c"), "simples": ("• simples", "#2a78d6"),
        "fachada": ("? só fachada", "#898781"), "alerta": ("! atenção", "#d03b3b")}
ORDEM = {"ok": 0, "simples": 1, "fachada": 2, "alerta": 3, None: 2}
MIN_AMOSTRA = 15                  # regiao so vira referencia com base suficiente
AREA_MAX = {1: 100, 2: 175, 3: 295}   # p99 real por quartos
AREA_MIN = 20
TOP = 24


def carregar():
    d = [x for x in json.load(open('raw_listings.json', encoding='utf-8'))
         if valid_price(x) and valid_geo(x)]
    d, _ = drop_outliers(d)
    for x in d:
        x['quadra'] = extract_quadra(x)
        x['bloco'] = extract_bloco(x)
    snap_para_quadra(d)
    d, _ = dedup(d)
    return d


def analisar():
    d = carregar()
    base = [x for x in d
            if x['operation'] == 'aluguel' and x['kind'] == 'apartamento'
            and x.get('area') and x['bedrooms'] in AREA_MAX
            and AREA_MIN < x['area'] <= AREA_MAX[x['bedrooms']]]
    for x in base:
        x['m2'] = x['price'] / x['area']
        x['total'] = x['price'] + (x.get('condo') or 0)
        x['m2_total'] = x['total'] / x['area']

    ref = {}
    por = defaultdict(list)
    for x in base:
        por[x['region']].append(x['m2'])
    for k, v in por.items():
        if len(v) >= MIN_AMOSTRA:
            ref[k] = st.median(v)

    cand, falsas = [], 0
    for x in base:
        r = ref.get(x['region'])
        if not r:
            continue
        x['ref'] = r
        x['desconto'] = (1 - x['m2'] / r) * 100
        # condominio conhecido que anula a vantagem => nao e pechincha
        if x.get('condo') and x['m2_total'] > r:
            falsas += 1
            continue
        cand.append(x)
    return base, cand, ref, falsas


def main():
    base, cand, ref, falsas = analisar()
    brl = lambda v: ('R$ ' + f'{v:,.0f}').replace(',', '.')
    brl2 = lambda v: ('R$ ' + f'{v:,.2f}').replace(',', 'X').replace('.', ',').replace('X', '.')

    regs = sorted(ref.items(), key=lambda kv: kv[1])
    top = sorted(cand, key=lambda z: -z['desconto'])[:TOP]
    melhores_reg = {}
    for x in cand:
        b = melhores_reg.get(x['region'])
        if not b or x['desconto'] > b['desconto']:
            melhores_reg[x['region']] = x

    print(f"base comparavel: {len(base)} | no ranking: {len(cand)} | "
          f"falsas pechinchas removidas pelo condominio: {falsas}")
    print("\nreferencia R$/m2 por regiao:")
    for k, v in regs:
        print(f"  {LABEL[k]:18s} {v:6.2f}")

    # ---------- cards ----------
    def card(x):
        cond = (f"cond. {brl(x['condo'])} · total {brl(x['total'])}"
                if x.get('condo') else "cond. não informado")
        foto = (f'<img src="{x["image"]}" alt="" loading="lazy">'
                if x.get('image') else '<div class="nofoto">sem foto</div>')
        local = (x.get('quadra') or '') + ((' Bl. ' + x['bloco']) if x.get('bloco') else '')
        av = AVALIACAO.get(x['url'])
        selo = obs = ''
        if av:
            txt, cor = SELO[av[0]]
            selo = f'<span class="selo" style="background:{cor}">{txt}</span>'
            obs = f'<div class="obs">{av[1]}</div>'
        return f"""<a class="card" href="{x['url']}" target="_blank" rel="noopener">
          <div class="foto">{foto}<span class="tag">{LABEL[x['region']]}</span>
            <span class="off">{x['desconto']:.0f}% abaixo</span>{selo}</div>
          <div class="corpo">
            <div class="preco">{brl(x['price'])}<span>/mês</span></div>
            <div class="cond">{cond}</div>
            <div class="local">{local or 'Localização não detalhada'}</div>
            <div class="meta">{x['bedrooms']} quartos · {x['area']:.0f} m² ·
              <b>{brl2(x['m2'])}/m²</b> <span class="ref">(região: {brl2(x['ref'])})</span></div>
            {obs}
            <div class="cta">ver anúncio ↗</div>
          </div></a>"""

    # os avaliados vem primeiro, do melhor estado para o pior
    top = sorted(top, key=lambda z: (ORDEM.get((AVALIACAO.get(z['url']) or (None,))[0]),
                                     -z['desconto']))
    cards_top = ''.join(card(x) for x in top)
    n_ok = sum(1 for x in top if (AVALIACAO.get(x['url']) or ('',))[0] == 'ok')
    n_alerta = sum(1 for x in top if (AVALIACAO.get(x['url']) or ('',))[0] == 'alerta')
    cards_reg = ''.join(card(melhores_reg[r['key']]) for r in REGIONS
                        if r['key'] in melhores_reg)

    maxref = max(v for _, v in regs)
    linhas_reg = ''.join(f"""<tr>
        <td>{LABEL[k]}</td>
        <td class="n">{brl2(v)}</td>
        <td class="barra"><i style="width:{v/maxref*100:.0f}%"></i></td>
        <td class="n">{sum(1 for x in base if x['region']==k)}</td></tr>""" for k, v in regs)

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Melhores custo-benefício de aluguel — DF</title>
<style>
:root{{color-scheme:light dark;--bg:#f7f7f5;--card:#fff;--ink:#111;--mut:#666;--line:#e4e4de;--ac:#2a78d6;--ok:#0ca30c}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--card:#1a1a19;--ink:#fff;--mut:#aaa;--line:#2c2c2a;--ac:#3987e5;--ok:#0ca30c}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:22px}}
.wrap{{max-width:1080px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:26px 0 4px}}
nav{{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-bottom:16px}}
nav a{{padding:7px 15px;font-size:13px;font-weight:700;text-decoration:none;color:var(--mut);background:var(--card)}}
nav a.on{{background:var(--ac);color:#fff}}
.sub{{color:var(--mut);font-size:13.5px;margin:0 0 6px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0 18px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin:16px 0}}
.k{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px}}
.k .l{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;font-weight:700}}
.k .v{{font-size:22px;font-weight:800;margin-top:4px;letter-spacing:-.5px}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(236px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;
  text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:transform .12s,box-shadow .12s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 8px 22px rgba(0,0,0,.16)}}
.foto{{position:relative;aspect-ratio:4/3;background:var(--bg);overflow:hidden}}
.foto img{{width:100%;height:100%;object-fit:cover;display:block}}
.nofoto{{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--mut);font-size:12px}}
.tag{{position:absolute;left:9px;bottom:9px;background:rgba(0,0,0,.72);color:#fff;
  font-size:10.5px;font-weight:700;padding:3px 8px;border-radius:6px}}
.off{{position:absolute;right:9px;top:9px;background:var(--ok);color:#fff;
  font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px}}
.selo{{position:absolute;left:9px;top:9px;color:#fff;font-size:10.5px;font-weight:800;
  padding:3px 8px;border-radius:6px}}
.obs{{font-size:12px;color:var(--ink);opacity:.82;margin-top:8px;line-height:1.35;
  border-top:1px solid var(--line);padding-top:7px}}
.corpo{{padding:12px 13px 13px}}
.preco{{font-size:19px;font-weight:800;letter-spacing:-.4px}}
.preco span{{font-size:12px;font-weight:600;color:var(--mut)}}
.cond{{font-size:12px;color:var(--mut);margin-top:2px}}
.local{{font-size:13px;font-weight:700;margin-top:7px}}
.meta{{font-size:12.5px;color:var(--mut);margin-top:2px}}
.meta .ref{{opacity:.8}}
.cta{{margin-top:10px;font-size:12.5px;font-weight:700;color:var(--ac)}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th,td{{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left}}
th{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.3px}}
td.n{{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap}}
td.barra{{width:45%}} td.barra i{{display:block;height:11px;background:var(--ac);border-radius:4px}}
.nota{{font-size:13px;color:var(--mut);border-left:3px solid var(--ac);padding:9px 12px;background:var(--card);border-radius:0 8px 8px 0;margin-top:14px}}
</style></head><body><div class="wrap">
<nav><a href="index.html">Mapa</a><a href="analise.html">Análise</a><a href="custo_beneficio.html" class="on">Custo-benefício</a></nav>
<h1>Melhores custo-benefício de aluguel</h1>
<p class="sub">Apartamentos no DF · coleta de {datetime.date.today().strftime('%d/%m/%Y')}
 · DFImóveis e Wimóveis, já deduplicadas</p>

<div class="kpis">
  <div class="k"><div class="l">Apartamentos comparáveis</div><div class="v">{len(base)}</div></div>
  <div class="k"><div class="l">No ranking</div><div class="v">{len(cand)}</div></div>
  <div class="k"><div class="l">Regiões com base</div><div class="v">{len(ref)}</div></div>
  <div class="k"><div class="l">Falsas pechinchas</div><div class="v">{falsas}</div></div>
  <div class="k"><div class="l">m² mais barato</div><div class="v">{brl2(regs[0][1])}</div></div>
  <div class="k"><div class="l">m² mais caro</div><div class="v">{brl2(regs[-1][1])}</div></div>
</div>

<div class="box">
  <b>Como esta lista foi montada</b>
  <p style="margin:8px 0 0;font-size:14px">Cada apartamento é comparado com o <b>m² típico da própria
  região</b>, não com o DF inteiro. Isso responde “onde vale a pena <i>aqui</i>” em vez de apenas apontar
  os bairros baratos — senão Taguatinga ganharia de todos e a Asa Norte nunca apareceria.
  O selo verde mostra quanto o anúncio está <b>abaixo do m² da sua região</b>.</p>
  <p style="margin:9px 0 0;font-size:14px">Ficaram de fora: <b>casas</b> (a área anunciada inclui o lote,
  então o m² não se compara), áreas implausíveis para o número de quartos (há “3 quartos de 9.768 m²”
  na base, que é a área do condomínio) e <b>{falsas} falsas pechinchas</b> — anúncios baratos por m²
  cujo condomínio informado levava o custo total acima da média da região.</p>
  <p style="margin:9px 0 0;font-size:14px">Por fim, <b>abri a foto de capa dos primeiros colocados</b>.
  É o passo que o número sozinho não dá: desconto grande quase sempre tem um motivo, e várias vezes o
  motivo está na imagem — unidade de subsolo, prédio comercial, ou uma capa que mostra só a vista para
  não mostrar o imóvel. O selo em cada card diz o que a foto revelou.</p>
</div>

<h2>O m² por região</h2>
<p class="sub">Mediana do aluguel por m², do mais barato ao mais caro. É o trade-off de localização.</p>
<div class="box"><table>
  <thead><tr><th>Região</th><th style="text-align:right">R$/m²</th><th></th><th style="text-align:right">Anúncios</th></tr></thead>
  <tbody>{linhas_reg}</tbody></table></div>

<h2>Os {len(top)} melhores negócios do DF</h2>
<p class="sub">Maior desconto sobre o m² da própria região — mas reordenados pelo que a
<b>foto do anúncio</b> revela. Abri a capa de cada um: {n_ok} mostram imóvel em bom estado
e {n_alerta} escondiam um problema que o preço sozinho não contava.</p>
<div class="grade">{cards_top}</div>

<h2>O melhor de cada região</h2>
<p class="sub">Para quem já sabe onde quer morar.</p>
<div class="grade">{cards_reg}</div>

<p class="nota">Desconto grande quase sempre tem um motivo que o anúncio não conta: andar baixo, sem
vaga, sem armários, precisando de reforma ou de frente para via movimentada. Trate a lista como
<b>onde olhar primeiro</b>, não como veredito. E lembre que <b>2 em cada 3 anúncios não informam o
condomínio</b> — nesses, o custo real é maior que o valor em destaque.</p>
</div></body></html>"""

    open('custo_beneficio.html', 'w', encoding='utf-8').write(html)
    print(f"\n-> custo_beneficio.html ({len(top)} no top, {len(melhores_reg)} regioes)")


if __name__ == '__main__':
    main()
