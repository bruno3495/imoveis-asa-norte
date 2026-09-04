# -*- coding: utf-8 -*-
"""
Confere se cada anuncio de raw_listings.json ainda esta no ar e remove os mortos.

Anuncio some do portal sem aviso; sem essa passada o painel mostra imovel que ja
foi alugado/vendido. Roda com poucas threads de proposito: o objetivo e nao levar
bloqueio por excesso de requisicao.

Uso:
  python validar.py            # valida tudo e reescreve raw_listings.json
  python validar.py --amostra  # so mede a taxa de mortos (nao altera nada)
"""
import json, re, sys, gzip, time, shutil, os, random, threading
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

import scrape

# Calibrado na marra: com 5 threads os portais devolviam 403 em 40% das chamadas
# (auto-bloqueio, que se disfarca de "anuncio morto"). Com 2 threads + 0,3 s a
# taxa de sucesso e 100%. Nao aumente sem medir de novo.
THREADS = 2
PAUSA = 0.3
TIMEOUT = 20

MORTO_TXT = re.compile(
    r'(im[oó]vel n[aã]o (foi )?encontrado|an[uú]ncio (n[aã]o|indispon)|'
    r'n[aã]o est[aá] mais dispon|removid[oa]|expirad[oa]|desativad[oa]|'
    r'p[aá]gina n[aã]o encontrada|aviso no disponible|no est[aá] disponible)', re.I)

_lock = threading.Lock()
_prog = {"n": 0, "morto": 0, "erro": 0}


def checar(url):
    """'ativo' | 'morto' | 'erro' — na duvida devolve 'erro' (nao descarta)."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": scrape.UA, "Accept-Encoding": "gzip",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            html = body.decode("utf-8", errors="ignore")
            if len(html) < 400:
                html = body.decode("latin-1", errors="ignore")
            return "morto" if MORTO_TXT.search(html[:250000]) else "ativo"
    except urllib.error.HTTPError as e:
        # 404/410 = saiu do ar. 403/429 = limite de taxa, nao e morte.
        return "morto" if e.code in (404, 410) else "erro"
    except Exception:
        return "erro"


def worker(x):
    v = checar(x["url"])
    with _lock:
        _prog["n"] += 1
        if v == "morto":
            _prog["morto"] += 1
        elif v == "erro":
            _prog["erro"] += 1
        if _prog["n"] % 250 == 0:
            print(f"  {_prog['n']} verificados | mortos {_prog['morto']} | erros {_prog['erro']}",
                  flush=True)
    time.sleep(3.0 if v == "erro" else PAUSA)   # recua forte se levou 403/timeout
    return v


def main():
    d = json.load(open("raw_listings.json", encoding="utf-8"))
    amostra = "--amostra" in sys.argv
    alvo = random.sample(d, min(200, len(d))) if amostra else d
    print(f"verificando {len(alvo)} de {len(d)} anuncios com {THREADS} threads...")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=THREADS) as ex:
        veredito = list(ex.map(worker, alvo))

    mortos = sum(1 for v in veredito if v == "morto")
    erros = sum(1 for v in veredito if v == "erro")
    print(f"\nresultado: {len(alvo)-mortos-erros} ativos | {mortos} mortos "
          f"({mortos/len(alvo):.1%}) | {erros} indefinidos ({(time.time()-t0)/60:.1f} min)")

    if amostra:
        print("(--amostra: nada foi alterado)")
        return

    vivos = [x for x, v in zip(alvo, veredito) if v != "morto"]
    if len(vivos) < len(d) * 0.5:
        raise SystemExit(f"ERRO: {mortos} mortos e demais da metade da base — "
                         f"cheira a bloqueio, nao a anuncio removido. Nada foi alterado.")

    shutil.copyfile("raw_listings.json", "raw_listings.bak.json")
    tmp = "raw_listings.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(vivos, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, "raw_listings.json")
    print(f"-> raw_listings.json: {len(d)} -> {len(vivos)} anuncios ({mortos} removidos)")


if __name__ == "__main__":
    main()
