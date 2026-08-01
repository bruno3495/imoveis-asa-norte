# Painel de Imóveis — Asa Norte (Brasília/DF)

Mapa estilo Airbnb com imóveis de **aluguel e compra** (1, 2 e 3 quartos) na Asa Norte,
coletados de **dfimoveis.com.br** e **wimoveis.com.br**, deduplicados (mantendo o **menor preço**
quando é o mesmo imóvel).

## Como usar

Abra **`index.html`** no navegador (duplo clique). É um arquivo único e autossuficiente
(os dados ficam embutidos), então funciona offline — só precisa de internet para carregar o mapa.

- **Ambos / Comprar / Alugar** — filtra por operação (azul = compra, verde = aluguel).
  No modo **Ambos**, cada quadra mostra **duas bolhas** (compra e aluguel), deslocadas para não sobrepor.
- **1 / 2 / 3 quartos** — liga/desliga cada opção
- **Preço máx** — sliders separados para compra e aluguel
- **Quadra** — digite p.ex. `SQN 214` (com autocompletar); o mapa centraliza na quadra
- **Fonte** — DFImóveis, Wimóveis ou todas
- Clique numa **bolha** para aproximar; clique numa **pill de preço** para ver o card com foto,
  detalhes e o link **“Ver anúncio original”**. Quando o mesmo imóvel aparece nos dois portais,
  o card mostra “Também anunciado em…”.

## Atualizar os dados

```bash
python scrape.py     # coleta os dois sites -> raw_listings.json
python build.py      # limpa preços, deduplica e gera index.html
```

## Arquivos

| Arquivo | O quê |
|---|---|
| `scrape.py` | Coleta paginada dos dois sites (usa o JSON estruturado embutido em cada página) |
| `build.py` | Limpeza de preço, deduplicação e geração do `index.html` |
| `raw_listings.json` | Dados brutos normalizados (antes da dedup) |
| `index.html` | **O painel** — mapa self-contained |

## Como funciona a coleta

- **dfimoveis**: lê o bloco `ld+json` (`ItemList`) de cada página `/{op}/df/brasilia/asa-norte/apartamento?pagina=N`.
- **wimoveis**: lê o `window.__PRELOADED_STATE__` de `/{op}/imoveis/df/brasilia/asa-norte?bedroom=N,N&page=N`.

## Deduplicação

Dois anúncios são considerados o mesmo imóvel quando têm **mesma operação + mesmo nº de quartos +
mesmas coordenadas (~11 m) + área equivalente (±2 m²)**. Nesse caso o mapa mostra apenas o de **menor preço**,
e os demais aparecem como “Também anunciado em…”. Esse critério é ajustável na função `dedup()` do `build.py`.

## Deploy (hospedar online)

Por ser um HTML único, dá para publicar em qualquer host estático:
arraste o `index.html` para [Netlify Drop](https://app.netlify.com/drop), ou suba num repositório
com **GitHub Pages**.
