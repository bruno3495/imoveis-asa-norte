# Painel de Imóveis — DF

Mapa estilo Airbnb com **apartamentos e casas** de **aluguel e compra** (1, 2 e 3 quartos),
coletados de **dfimoveis.com.br** e **wimoveis.com.br**, deduplicados (mantendo o **menor preço**
quando é o mesmo imóvel).

**Regiões cobertas:** Asa Norte, Asa Sul, Jardim Botânico, Sobradinho, Grande Colorado,
Guará I, Águas Claras e Taguatinga.

## Como usar

Abra **`index.html`** no navegador (duplo clique). É um arquivo único e autossuficiente
(os dados ficam embutidos), então funciona offline — só precisa de internet para carregar o mapa.

- **Ambos / Comprar / Alugar** — filtra por operação (azul = compra, verde = aluguel).
  No modo **Ambos**, cada ponto mostra **duas bolhas** (compra e aluguel), deslocadas para não sobrepor.
- **Região** — uma das 8 regiões ou todas; ao escolher, o mapa se reenquadra
- **Apto / Casa** — liga/desliga cada tipo
- **1q / 2q / 3q** — liga/desliga cada opção
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

As regiões, com o slug de cada site, ficam na lista `REGIONS` no topo do `scrape.py` —
é lá que se adiciona/remove região.

- **dfimoveis**: lê o bloco `ld+json` (`ItemList`) de
  `/{op}/df/{cidade[/bairro]}/{apartamento|casa}/{N}-quartos?pagina=N`.
- **wimoveis**: lê o `window.__PRELOADED_STATE__` de
  `/{op}/imoveis/df/{regiao}?bedroom=N,N&page=N`. Como o site às vezes cai no
  resultado da cidade inteira, cada anúncio é conferido contra os `tokens` de
  nome de localidade da região (descarta bairro vizinho).

Os dois sites filtram quartos na própria URL, o que reduz muito a paginação.

## Deduplicação

Dois anúncios são considerados o mesmo imóvel quando têm **mesma operação + mesmo nº de quartos +
mesmas coordenadas (~11 m) + área equivalente (±2 m²)**. Nesse caso o mapa mostra apenas o de **menor preço**,
e os demais aparecem como “Também anunciado em…”. Esse critério é ajustável na função `dedup()` do `build.py`.

## Atualização automática (agendada)

- **Onde roda:** localmente, via **Tarefa Agendada do Windows** "Atualizar Imoveis Asa Norte"
  (semanal, segunda 09:00; roda quando o PC ligar, se estiver desligado no horário).
  Chama `run_update.bat` → `update.py`.
- **Por que local e não na nuvem:** o `wimoveis.com.br` bloqueia IPs de data center
  (`HTTP 403`), então GitHub Actions não consegue coletar. Do seu PC (IP residencial) funciona.
- Cada execução bem-sucedida grava um "batimento" em `last_run.txt` e faz commit/push.

## Monitoramento / alerta por e-mail

O workflow `.github/workflows/monitor.yml` roda no GitHub Actions (quarta 15:00 BRT) e **não coleta nada** —
só confere se `last_run.txt` foi atualizado nos últimos 8 dias. Se estiver velho (PC não ligou, tarefa falhou),
o job **falha** e o GitHub envia e-mail automático.

Para receber o alerta, no GitHub: **Settings → Emails** (adicione/verifique seu e-mail) e
**Settings → Notifications → Actions** (marque e-mail, opção "Only notify for failed workflows").

## Deploy (hospedar online)

Por ser um HTML único, dá para publicar em qualquer host estático:
arraste o `index.html` para [Netlify Drop](https://app.netlify.com/drop), ou suba num repositório
com **GitHub Pages**.
