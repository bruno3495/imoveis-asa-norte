# Painel de Imóveis — DF

Mapa estilo Airbnb com **apartamentos e casas** de **aluguel e compra** (1, 2 e 3 quartos),
coletados de **dfimoveis.com.br** e **wimoveis.com.br**, deduplicados (mantendo o **menor preço**
quando é o mesmo imóvel).

**Regiões cobertas:** Asa Norte, Asa Sul, Jardim Botânico, Sobradinho, Grande Colorado,
Guará I, Águas Claras e Taguatinga.

## Como usar

Duas páginas, ligadas pelas abas **Mapa | Análise** no topo:

- **`index.html`** — o mapa com os anúncios
- **`analise.html`** — a análise exploratória (preços, R$/m², rentabilidade, distribuições)

Abra qualquer uma no navegador (duplo clique). São arquivos únicos e autossuficientes
(os dados ficam embutidos); só precisam de internet para carregar os tiles do mapa.

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
| `build_eda.py` | Gera o `analise.html` (EDA) a partir da mesma base limpa |
| `raw_listings.json` | Dados brutos normalizados (antes da dedup) |
| `raw_listings.bak.json` | Backup automático da última coleta boa |
| `index.html` | **O painel** — mapa self-contained |
| `analise.html` | **A análise** — gráficos, self-contained |

## Duas salvaguardas que já pagaram por si

1. **A coleta nunca sobrescreve dados bons.** Em 31/08/2026 a tarefa agendada rodou
   logo após o boot, sem DNS: as 904 requisições falharam e o `raw_listings.json`
   virou `[]`, levando junto 17.691 anúncios (recuperados do git). Agora o `scrape.py`
   testa a rede antes de começar, aborta se a coleta vier vazia ou com >50% de erro,
   guarda backup e grava de forma atômica.
2. **O `update.py` não publica coleta suspeita** — piso absoluto por portal e queda
   máxima de 45% vs. `last_counts.json`.

> **Tiles do mapa:** a CARTO passou a exigir API key (servia os tiles com a marca
> d'água "API KEY REQUIRED"). O mapa usa a base cinza-clara da **Esri**, que não
> pede chave. Se um dia ela também mudar, o ponto de troca é a chamada
> `L.tileLayer(...)` no template do `build.py`.

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
