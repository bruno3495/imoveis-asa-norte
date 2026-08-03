---
name: atualizar-imoveis
description: Atualiza o painel de imóveis do DF — re-coleta dfimoveis.com.br e wimoveis.com.br, deduplica, regenera o mapa e publica no GitHub Pages. Use quando o Bruno pedir "atualizar imóveis", "rodar de novo", "coletar dados novos", "republicar o painel/mapa" ou similar.
---

# Atualizar o painel de imóveis (DF)

Projeto: coleta apartamentos e casas de aluguel e compra (1–3 quartos) a partir de
`dfimoveis.com.br` e `wimoveis.com.br`, deduplica (mantendo o menor preço) e publica
um mapa estilo Airbnb no GitHub Pages.

Regiões (lista `REGIONS` no topo do `scrape.py`): Asa Norte, Asa Sul, Jardim Botânico,
Sobradinho, Grande Colorado, Guará I, Águas Claras, Taguatinga.
A coleta completa leva **~30–50 min** — rode em background e acompanhe.

- **Site ao vivo:** https://bruno3495.github.io/imoveis-asa-norte/
- **Repositório:** https://github.com/bruno3495/imoveis-asa-norte
- **Pasta local:** a raiz deste projeto (onde estão `scrape.py`, `build.py`, `update.py`)

## Passos

1. **Rodar a atualização completa:**
   ```bash
   python update.py
   ```
   Isso faz: `scrape.py` → valida a saúde da coleta → `build.py` → `git commit` → `git push`.
   O `update.py` **aborta antes de publicar** se a coleta de algum portal cair abaixo do
   esperado (sinal de que o site mudou de estrutura).

2. **Se `update.py` abortar por coleta suspeita** (piso absoluto ou queda >45% vs
   `last_counts.json`, sinal de portal quebrado):
   - Baixe uma página do portal afetado e inspecione a estrutura de dados embutida:
     - dfimoveis: bloco `<script type="application/ld+json">` do tipo `ItemList`.
     - wimoveis: `window.__PRELOADED_STATE__` → `listStore.listPostings`.
   - Ajuste o parser correspondente em `scrape.py` (`parse_dfimoveis` / `parse_wimoveis`)
     ou os slugs/paginação em `REGIONS`, então rode `python update.py` de novo.
   - Dá para testar uma região só: `python scrape.py aguas-claras`.
   - Só publique quando os números voltarem ao patamar normal (milhares por portal).

3. **Confirmar a publicação:**
   - O push dispara o rebuild do Pages (~1 min).
   - Verifique o status: `gh` (em `C:\Program Files\GitHub CLI\gh.exe`)
     `api repos/bruno3495/imoveis-asa-norte/pages/builds/latest --jq .status` deve dar `built`.
   - Cheque o HTTP: `curl -s -o /dev/null -w "%{http_code}" -L https://bruno3495.github.io/imoveis-asa-norte/` → `200`.

4. **Relatar ao Bruno** (em português), de forma curta:
   - Total coletado e por portal, com o diff vs. a rodada anterior (o `update.py` imprime `antes -> depois`).
   - Nº de imóveis únicos após dedup (aparece na saída do `build.py`).
   - Confirmação de que o site foi republicado + o link.

## Observações

- Autenticação do GitHub já está configurada (Git Credential Manager + `gh` logado como `bruno3495`).
  Se o push pedir login, o token expirou — peça ao Bruno rodar `gh auth login` (ele autoriza no navegador).
- Os dados são um retrato do momento da coleta; cada execução substitui `raw_listings.json` e `index.html`.
- Para gerar sem publicar (teste): `python update.py --no-push`.
- A heurística de dedup fica na função `dedup()` do `build.py` (operação + quartos + coords ~11 m + área ±2 m²).
