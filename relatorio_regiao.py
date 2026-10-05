# -*- coding: utf-8 -*-
"""
Relatorio de uma regiao, com fotos: as melhores opcoes de aluguel, o perfil do
estoque local e o custo de vida (aluguel + condominio + gasolina ate o trabalho).

Uso:
  python relatorio_regiao.py lago-norte
  python relatorio_regiao.py sobradinho --top 16

Gera relatorio_<regiao>.html. As chaves validas estao em REGIONS (scrape.py).
"""
import sys, statistics as st, datetime
from collections import Counter

from scrape import REGIONS
from custo_beneficio import (analisar, custo_combustivel, LABEL, TRABALHO,
                             PRECO_LITRO, CONSUMO_KML, AVALIACAO, SELO, ORDEM)

# Observacoes escritas depois de abrir a foto de capa de cada anuncio.
# Mora aqui, e nao no custo_beneficio, porque sao imoveis especificos desta
# regiao — o dicionario de la cobre o top geral do DF.
AVALIACAO_REGIAO = {
 "https://www.wimoveis.com.br/propriedades/shin-ca-02-ed.-garden-place-3042583062.html":
   ("ok", "Prédio baixo bem conservado, com jardim e palmeiras. A foto é da fachada — o interior não aparece."),
 "https://www.dfimoveis.com.br/imovel/apartamento-2-quartos-aluguel-lago-norte-brasilia-df-ca-09-1171129":
   ("ok", "Duplex com escada interna, paredes limpas, piso em bom estado e luminárias embutidas. A melhor opção de 2 quartos."),
 "https://www.wimoveis.com.br/propriedades/ca-11-ed-next-duplex-3044280289.html":
   ("ok", "Duplex claro e bem conservado, 90 m². Mas o condomínio de R$ 1.060 é 42% do aluguel — é ele que pesa no custo de vida."),
 "https://www.dfimoveis.com.br/imovel/apartamento-2-quartos-aluguel-lago-norte-brasilia-df-ca-02-1342921":
   ("ok", "Edifício Maison do Lago, fachada cuidada e gramado. Anúncio diz mobiliado e com garagem."),
 "https://www.dfimoveis.com.br/imovel/apartamento-2-quartos-aluguel-lago-norte-brasilia-df-ca-02-1443416":
   ("fachada", "Prédio dos anos 80/90 em azulejo verde, conservado. Só a fachada — o interior não foi mostrado."),
 "https://www.dfimoveis.com.br/imovel/apartamento-2-quartos-aluguel-lago-norte-brasilia-df-via-varjao-do-torto-1185807":
   ("alerta", "Está marcado como Lago Norte, mas o endereço é Via Varjão do Torto — o Varjão, região vizinha e bem diferente dos CAs. A foto mostra parede nua com fiação solta na tomada."),
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        raise SystemExit(f"informe a regiao: {[r['key'] for r in REGIONS]}")
    alvo = args[0]
    if alvo not in {r["key"] for r in REGIONS}:
        raise SystemExit(f"regiao desconhecida. validas: {[r['key'] for r in REGIONS]}")
    topn = 16
    if "--top" in sys.argv:
        topn = int(sys.argv[sys.argv.index("--top") + 1])

    base, cand, ref, falsas, origem = analisar()
    reg = [x for x in base if x["region"] == alvo]
    regc = [x for x in cand if x["region"] == alvo]
    if not reg:
        raise SystemExit(f"sem apartamentos de aluguel comparaveis em {LABEL[alvo]}")
    r = ref.get(alvo)

    aval = dict(AVALIACAO)
    aval.update(AVALIACAO_REGIAO)

    # melhores primeiro, mas quem a foto reprovou desce
    top = sorted(regc, key=lambda z: -z["desconto"])[:topn]
    top.sort(key=lambda z: (ORDEM.get((aval.get(z["url"]) or (None,))[0]), -z["desconto"]))

    brl = lambda v: ("R$ " + f"{v:,.0f}").replace(",", ".") if v is not None else "—"
    brl2 = lambda v: ("R$ " + f"{v:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")

    qtos = Counter(x["bedrooms"] for x in reg)
    dist = st.median([x["dist"] for x in reg if x.get("dist") is not None])
    area_med = st.median([x["area"] for x in reg])
    alug_med = st.median([x["price"] for x in reg])
    comc = [x for x in reg if x.get("condo")]
    vida_min = min(x["custo_vida"] for x in regc) if regc else None

    cards = ""
    for x in top:
        cond = (f"cond. {brl(x['condo'])} · total {brl(x['total'])}"
                if x.get("condo") else "cond. não informado")
        foto = (f'<img src="{x["image"]}" alt="" loading="lazy">'
                if x.get("image") else '<div class="nofoto">sem foto</div>')
        local = (x.get("quadra") or "") + ((" Bl. " + x["bloco"]) if x.get("bloco") else "")
        a = aval.get(x["url"])
        selo = obs = ""
        if a:
            txt, cor = SELO[a[0]]
            selo = f'<span class="selo" style="background:{cor}">{txt}</span>'
            obs = f'<div class="obs">{a[1]}</div>'
        cards += f"""<a class="card" href="{x['url']}" target="_blank" rel="noopener">
          <div class="foto">{foto}<span class="off">{x['desconto']:.0f}% abaixo</span>{selo}</div>
          <div class="corpo">
            <div class="preco">{brl(x['price'])}<span>/mês</span></div>
            <div class="cond">{cond}</div>
            <div class="local">{local or 'Localização não detalhada'}</div>
            <div class="meta">{x['bedrooms']} quarto{'s' if x['bedrooms']>1 else ''} ·
              {x['area']:.0f} m² · <b>{brl2(x['m2'])}/m²</b></div>
            <div class="desl">🚗 {x['dist']:.1f} km · {brl(x['gas'])} de gasolina ·
              <b>custo de vida {brl(x['custo_vida'])}</b></div>
            {obs}
            <div class="cta">ver anúncio ↗</div>
          </div></a>"""

    perfil = " · ".join(f"{n} de {q} quarto{'s' if q>1 else ''}"
                        for q, n in sorted(qtos.items()))
    falta3 = "" if qtos.get(3) else (
        "<b>Não há nenhum 3 quartos</b> no conjunto comparável. ")

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{LABEL[alvo]} — aluguel com fotos</title>
<style>
:root{{color-scheme:light dark;--bg:#f7f7f5;--card:#fff;--ink:#111;--mut:#666;--line:#e4e4de;--ac:#2a78d6;--ok:#0ca30c}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--card:#1a1a19;--ink:#fff;--mut:#aaa;--line:#2c2c2a;--ac:#3987e5}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:22px}}
.wrap{{max-width:1080px;margin:0 auto}}
nav{{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-bottom:16px}}
nav a{{padding:7px 15px;font-size:13px;font-weight:700;text-decoration:none;color:var(--mut);background:var(--card)}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:24px 0 10px}}
.sub{{color:var(--mut);font-size:13.5px;margin:0 0 16px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin-bottom:16px}}
.k{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px}}
.k .l{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;font-weight:700}}
.k .v{{font-size:22px;font-weight:800;margin-top:4px;letter-spacing:-.5px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:18px}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(236px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;
  text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:transform .12s,box-shadow .12s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 8px 22px rgba(0,0,0,.16)}}
.foto{{position:relative;aspect-ratio:4/3;background:var(--bg);overflow:hidden}}
.foto img{{width:100%;height:100%;object-fit:cover;display:block}}
.nofoto{{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--mut);font-size:12px}}
.off{{position:absolute;right:9px;top:9px;background:var(--ok);color:#fff;font-size:11px;font-weight:800;padding:3px 8px;border-radius:6px}}
.selo{{position:absolute;left:9px;top:9px;color:#fff;font-size:10.5px;font-weight:800;padding:3px 8px;border-radius:6px}}
.corpo{{padding:12px 13px 13px}}
.preco{{font-size:19px;font-weight:800;letter-spacing:-.4px}}
.preco span{{font-size:12px;font-weight:600;color:var(--mut)}}
.cond{{font-size:12px;color:var(--mut);margin-top:2px}}
.local{{font-size:13px;font-weight:700;margin-top:7px}}
.meta{{font-size:12.5px;color:var(--mut);margin-top:2px}}
.desl{{font-size:12px;color:var(--mut);margin-top:6px}}
.obs{{font-size:12px;opacity:.85;margin-top:8px;line-height:1.35;border-top:1px solid var(--line);padding-top:7px}}
.cta{{margin-top:10px;font-size:12.5px;font-weight:700;color:var(--ac)}}
.nota{{font-size:13px;color:var(--mut);border-left:3px solid var(--ac);padding:9px 12px;background:var(--card);border-radius:0 8px 8px 0;margin-top:16px}}
</style></head><body><div class="wrap">
<nav><a href="index.html">Mapa</a><a href="analise.html">Análise</a>
<a href="custo_beneficio.html">Custo-benefício</a><a href="unb.html">UnB</a></nav>
<h1>{LABEL[alvo]} — aluguel de apartamentos</h1>
<p class="sub">{len(reg)} anúncios comparáveis · coleta de {datetime.date.today().strftime('%d/%m/%Y')}
 · distância medida até a <b>{TRABALHO}</b></p>

<div class="kpis">
  <div class="k"><div class="l">Anúncios</div><div class="v">{len(reg)}</div></div>
  <div class="k"><div class="l">Aluguel mediano</div><div class="v">{brl(alug_med)}</div></div>
  <div class="k"><div class="l">Área mediana</div><div class="v">{area_med:.0f} m²</div></div>
  <div class="k"><div class="l">m² da região</div><div class="v">{brl2(r)}</div></div>
  <div class="k"><div class="l">Distância</div><div class="v">{dist:.1f} km</div></div>
  <div class="k"><div class="l">Menor custo de vida</div><div class="v">{brl(vida_min)}</div></div>
</div>

<div class="box">
  <b>O perfil do estoque</b>
  <p style="margin:8px 0 0;font-size:14px">São {perfil}. {falta3}Isso importa mais que o preço:
  a região resolve bem quem quer <b>morar perto pagando pouco</b>, e resolve mal quem precisa de
  espaço. O “custo de vida” de cada card soma aluguel + condomínio + gasolina
  ({CONSUMO_KML:.0f} km/l a {brl2(PRECO_LITRO)}/l, {TRABALHO} como destino).</p>
  <p style="margin:9px 0 0;font-size:14px">O condomínio aparece em apenas
  <b>{len(comc)} dos {len(reg)}</b> anúncios{(', com mediana de ' + brl(st.median([x['condo'] for x in comc]))) if comc else ''} —
  onde ele não é informado, o custo real é maior que o valor em destaque.</p>
</div>

<h2>As {len(top)} melhores opções</h2>
<p class="sub">Ordenadas pelo desconto sobre o m² da região, mas reordenadas pelo que a foto revelou.</p>
<div class="grade">{cards}</div>

<p class="nota">Desconto grande costuma ter um motivo que o anúncio não conta — andar baixo, sem vaga,
sem armários ou precisando de reforma. Use como <b>onde olhar primeiro</b>, não como veredito.
Preços mudam e anúncios saem do ar: confirme no link.</p>
</div></body></html>"""

    nome = f"relatorio_{alvo}.html"
    open(nome, "w", encoding="utf-8").write(html)
    print(f"-> {nome} ({len(top)} opcoes de {len(reg)} anuncios)")
    print(f"   aluguel mediano {brl(alug_med)} | area {area_med:.0f} m2 | "
          f"{dist:.1f} km | menor custo de vida {brl(vida_min)}")


if __name__ == "__main__":
    main()
