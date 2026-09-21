# -*- coding: utf-8 -*-
"""
Monitor dos imoveis residenciais da UnB (SPI) — https://imoveisunb.unb.br

Sao poucos imoveis e eles giram rapido: aparecem e somem em dias. Entao o valor
aqui nao e um painel, e sim AVISAR quando surge algo novo — e dizer se o novo
presta, comparando com o mercado da regiao e com o custo de deslocamento.

Os anuncios sao posts do WordPress, com dados limpos (endereco com bloco e
apartamento, valor, area util, quartos, vagas, condominio). Duas categorias
interessam:
  22 = Residencial com Fila Virtual      15 = Residencial sem Fila Virtual
  (a categoria 1, "Indisponivel", e o arquivo do que ja saiu)

Uso:
  python unb.py            # verifica, atualiza o estado e gera unb.html
  python unb.py --quieto   # so imprime se houver novidade (para agendamento)
"""
import json, re, sys, html as H, os, statistics as st, datetime

import scrape
from build import valid_price, valid_geo, extract_quadra, km
from custo_beneficio import custo_combustivel, TRABALHO, PRECO_LITRO, CONSUMO_KML

API = "https://imoveisunb.unb.br/wp-json/wp/v2"
CATEGORIAS = "22,15"
ESTADO = "unb_estado.json"

# a partir de quanto abaixo do mercado da regiao o imovel vira "muito bom"
LIMITE_OTIMO = 20.0      # % abaixo do R$/m2 da regiao, ja com condominio


def buscar():
    b = scrape.fetch(f"{API}/posts?categories={CATEGORIAS}&per_page=50", tries=3)
    if not b:
        raise SystemExit("ERRO: nao consegui acessar o site da UnB. Nada foi alterado.")
    return json.loads(b.decode("utf-8", errors="ignore"))


def num(txt):
    """'R$ 6.007,00' ou '129,65 m²' -> float"""
    if not txt:
        return None
    t = re.sub(r"[^\d,.]", "", txt).replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parsear(post):
    titulo = H.unescape(re.sub(r"<[^>]+>", "", post["title"]["rendered"])).strip()
    corpo = H.unescape(re.sub(r"<[^>]+>", " ", post["content"]["rendered"]))
    corpo = re.sub(r"\s+", " ", corpo)

    def campo(rotulo, rx=r"([\d\.,]+)"):
        m = re.search(rotulo + r"\s*:?\s*(?:R\$)?\s*" + rx, corpo, re.I)
        return m.group(1) if m else None

    return {
        "id": post["id"],
        "titulo": titulo,
        "url": post["link"],
        "data": post["date"][:10],
        "com_fila": 22 in post.get("categories", []),
        "preco": num(campo(r"Valor de loca[çc][ãa]o")),
        "area": num(campo(r"[ÁA]rea [ÚU]til")),
        "quartos": int(num(campo(r"Quartos")) or 0) or None,
        "vagas": int(num(campo(r"Vagas")) or 0) or None,
        "condo": num(campo(r"Condom[íi]nio")),
        "quadra": extract_quadra({"address": titulo, "title": titulo}),
    }


def referencias():
    """R$/m2 de aluguel e coordenada de cada quadra, a partir da base do painel."""
    if not os.path.exists("raw_listings.json"):
        return {}, {}, None
    d = [x for x in json.load(open("raw_listings.json", encoding="utf-8"))
         if valid_price(x) and valid_geo(x)]
    for x in d:
        x["quadra"] = extract_quadra(x)

    m2 = {}
    porreg = {}
    for x in d:
        if (x["operation"] == "aluguel" and x["kind"] == "apartamento"
                and x.get("area") and 20 < x["area"] < 400):
            porreg.setdefault(x["region"], []).append(x["price"] / x["area"])
    for k, v in porreg.items():
        if len(v) >= 15:
            m2[k] = st.median(v)

    coords = {}
    porq = {}
    for x in d:
        if x.get("quadra"):
            porq.setdefault(x["quadra"], []).append(x)
    for q, g in porq.items():
        if len(g) >= 3:
            coords[q] = (st.median([y["lat"] for y in g]),
                         st.median([y["lon"] for y in g]))

    origem = coords.get(TRABALHO)
    return m2, coords, origem


def regiao_da_quadra(q):
    if not q:
        return None
    if q.startswith(("SQN", "CLN", "SCRN", "SHCGN", "SGAN", "SCLRN", "SQNW")):
        return "asa-norte"
    if q.startswith(("SQS", "CLS", "CRS", "SHCS", "SGAS")):
        return "asa-sul"
    return None


def avaliar(im, m2ref, coords, origem):
    """Compara com o mercado da regiao e calcula o custo de deslocamento."""
    im["regiao"] = regiao_da_quadra(im.get("quadra"))
    ref = m2ref.get(im["regiao"])
    im["ref_m2"] = ref
    if im.get("preco") and im.get("area"):
        im["m2"] = im["preco"] / im["area"]
        im["total"] = im["preco"] + (im.get("condo") or 0)
        im["m2_total"] = im["total"] / im["area"]
        if ref:
            im["desconto"] = (1 - im["m2"] / ref) * 100
            im["desconto_total"] = (1 - im["m2_total"] / ref) * 100
    if origem and im.get("quadra") in coords:
        c = coords[im["quadra"]]
        im["dist"] = km(origem[0], origem[1], c[0], c[1])
        im["gas"] = custo_combustivel(im["dist"])
        im["custo_vida"] = im.get("total", im.get("preco") or 0) + im["gas"]
    return im


def e_otimo(im):
    """Vale um aviso? Barato mesmo depois do condominio, ou colado no trabalho."""
    d = im.get("desconto_total")
    perto = im.get("dist") is not None and im["dist"] <= 1.5
    return (d is not None and d >= LIMITE_OTIMO) or perto


def carregar_estado():
    if os.path.exists(ESTADO):
        try:
            return json.load(open(ESTADO, encoding="utf-8"))
        except Exception:
            pass
    return {"vistos": [], "atualizado": None}


def main():
    quieto = "--quieto" in sys.argv
    posts = buscar()
    imoveis = [parsear(p) for p in posts]
    m2ref, coords, origem = referencias()
    imoveis = [avaliar(im, m2ref, coords, origem) for im in imoveis]
    imoveis.sort(key=lambda z: -(z.get("desconto_total") or -999))

    estado = carregar_estado()
    vistos = set(estado.get("vistos", []))
    novos = [im for im in imoveis if im["id"] not in vistos]
    sumiram = len(vistos - {im["id"] for im in imoveis})

    brl = lambda v: ("R$ " + f"{v:,.0f}").replace(",", ".") if v is not None else "—"

    if not quieto or novos:
        print(f"UnB · {len(imoveis)} imóveis disponíveis "
              f"({sum(1 for i in imoveis if i['com_fila'])} com fila virtual)")
        if estado.get("atualizado"):
            print(f"última verificação: {estado['atualizado']} | "
                  f"novos desde então: {len(novos)} | saíram: {sumiram}")
        print()
        for im in imoveis:
            marca = "NOVO " if im["id"] in {n["id"] for n in novos} else "     "
            estrela = " ★ MUITO BOM" if e_otimo(im) else ""
            print(f"{marca}{im['titulo']:22s} {brl(im.get('preco')):>11s} "
                  f"+ cond {brl(im.get('condo')):>10s} | "
                  f"{(str(im.get('area')) + ' m²') if im.get('area') else '—':>10s} "
                  f"{im.get('quartos') or '?'}q", end="")
            if im.get("desconto_total") is not None:
                print(f" | {im['desconto_total']:+.0f}% vs mercado", end="")
            if im.get("dist") is not None:
                print(f" | {im['dist']:.1f} km ({brl(im['gas'])} gas)", end="")
            print(estrela)

    if novos:
        print(f"\n>>> {len(novos)} NOVO(S):")
        for im in novos:
            print(f"    {im['titulo']} — {brl(im.get('preco'))} — {im['url']}")
        bons = [im for im in novos if e_otimo(im)]
        if bons:
            print(f"\n>>> {len(bons)} MERECE(M) ATENÇÃO AGORA:")
            for im in bons:
                print(f"    ★ {im['titulo']}: {brl(im.get('preco'))} + cond "
                      f"{brl(im.get('condo'))} | {im.get('desconto_total', 0):+.0f}% vs mercado")
                print(f"      {im['url']}")
    elif not quieto:
        print("\nNenhuma novidade desde a última verificação.")

    json.dump({"vistos": [im["id"] for im in imoveis],
               "atualizado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
               "detalhe": imoveis},
              open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    gerar_html(imoveis, novos, estado)
    return 0


def gerar_html(imoveis, novos, estado):
    brl = lambda v: ("R$ " + f"{v:,.0f}").replace(",", ".") if v is not None else "—"
    ids_novos = {n["id"] for n in novos}
    linhas = ""
    for im in imoveis:
        selo = ""
        if im["id"] in ids_novos:
            selo += '<span class="s novo">novo</span>'
        if e_otimo(im):
            selo += '<span class="s bom">muito bom</span>'
        d = im.get("desconto_total")
        cls = "pos" if (d or 0) > 0 else "neg"
        linhas += f"""<tr>
          <td><a href="{im['url']}" target="_blank" rel="noopener">{im['titulo']}</a>{selo}
            <div class="sub2">{'com fila virtual' if im['com_fila'] else 'sem fila virtual'} · {im['data']}</div></td>
          <td class="n">{brl(im.get('preco'))}</td>
          <td class="n">{brl(im.get('condo'))}</td>
          <td class="n"><b>{brl(im.get('total'))}</b></td>
          <td class="n">{(f"{im['area']:.0f} m²") if im.get('area') else '—'}</td>
          <td class="n">{im.get('quartos') or '—'}</td>
          <td class="n {cls}">{(f"{d:+.0f}%") if d is not None else '—'}</td>
          <td class="n">{(f"{im['dist']:.1f} km") if im.get('dist') is not None else '—'}</td>
          <td class="n">{brl(im.get('custo_vida'))}</td></tr>"""

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Imóveis da UnB — monitor</title>
<style>
:root{{color-scheme:light dark;--bg:#f7f7f5;--card:#fff;--ink:#111;--mut:#666;--line:#e4e4de;--ac:#2a78d6;--ok:#0ca30c}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--card:#1a1a19;--ink:#fff;--mut:#aaa;--line:#2c2c2a;--ac:#3987e5}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:22px}}
.wrap{{max-width:1080px;margin:0 auto}}
nav{{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-bottom:16px}}
nav a{{padding:7px 15px;font-size:13px;font-weight:700;text-decoration:none;color:var(--mut);background:var(--card)}}
nav a.on{{background:var(--ac);color:#fff}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:var(--mut);font-size:13.5px;margin:0 0 18px}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.3px}}
td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.pos{{color:var(--ok);font-weight:700}} td.neg{{color:#d03b3b}}
a{{color:var(--ac);text-decoration:none;font-weight:600}}
.s{{display:inline-block;font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;margin-left:6px;color:#fff}}
.s.novo{{background:var(--ac)}} .s.bom{{background:var(--ok)}}
.sub2{{font-size:11.5px;color:var(--mut);font-weight:400;margin-top:2px}}
.nota{{font-size:13px;color:var(--mut);border-left:3px solid var(--ac);padding:9px 12px;background:var(--card);border-radius:0 8px 8px 0}}
</style></head><body><div class="wrap">
<nav><a href="index.html">Mapa</a><a href="analise.html">Análise</a>
<a href="custo_beneficio.html">Custo-benefício</a><a href="unb.html" class="on">UnB</a></nav>
<h1>Imóveis residenciais da UnB</h1>
<p class="sub">{len(imoveis)} disponíveis · verificado em {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}
 · fonte: <a href="https://imoveisunb.unb.br/" target="_blank">SPI/UnB</a></p>

<div class="box">
  <b>Por que vale monitorar</b>
  <p style="margin:8px 0 0;font-size:14px">São poucos imóveis e eles giram rápido — aparecem e somem em
  dias. O “% vs mercado” compara o <b>custo total</b> (aluguel + condomínio) por m² com o que se paga
  na mesma região nos portais. A distância é até a <b>{TRABALHO}</b>, e o “custo de vida” soma
  aluguel + condomínio + gasolina ({CONSUMO_KML:.0f} km/l a {("R$ " + f"{PRECO_LITRO:.2f}").replace(".", ",")}/l).</p>
</div>

<table>
  <thead><tr><th>Imóvel</th><th style="text-align:right">Aluguel</th>
  <th style="text-align:right">Condomínio</th><th style="text-align:right">Total</th>
  <th style="text-align:right">Área</th><th style="text-align:right">Qtos</th>
  <th style="text-align:right">vs mercado</th><th style="text-align:right">Distância</th>
  <th style="text-align:right">Custo de vida</th></tr></thead>
  <tbody>{linhas}</tbody></table>

<p class="nota" style="margin-top:16px">O condomínio informado pela UnB é aproximado — confirme com a
administradora. Imóveis “com fila virtual” exigem inscrição em horário específico; os “sem fila” são
por ordem de chegada na SPI, com visitação nas quartas até as 14h.</p>
</div></body></html>"""
    open("unb.html", "w", encoding="utf-8").write(html)
    print(f"\n-> unb.html gerado")


if __name__ == "__main__":
    sys.exit(main())
