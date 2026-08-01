# -*- coding: utf-8 -*-
"""
Atualiza o painel de imoveis de ponta a ponta:
  1. coleta os dois sites            (scrape.py -> raw_listings.json)
  2. deduplica e gera o mapa         (build.py  -> index.html)
  3. versiona e publica no Pages     (git commit + push)

Uso:
  python update.py            # coleta, gera, commita e faz push
  python update.py --no-push  # so coleta e gera (nao publica)

Retorna codigo de saida != 0 se algo falhar (util p/ agendamento).
"""
import subprocess, sys, json, os, datetime, re

HERE = os.path.dirname(os.path.abspath(__file__))
# limites de sanidade: se cair abaixo disso, provavelmente um site mudou de estrutura
MIN_ESPERADO = {"dfimoveis": 300, "wimoveis": 300}


def run(cmd, **kw):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=HERE, **kw)
    if r.returncode != 0:
        raise SystemExit(f"ERRO: comando falhou ({r.returncode}): {' '.join(cmd)}")
    return r


def count_by_source(path):
    if not os.path.exists(path):
        return {}
    data = json.load(open(path, encoding="utf-8"))
    out = {}
    for x in data:
        out[x["source"]] = out.get(x["source"], 0) + 1
    return out


def main():
    push = "--no-push" not in sys.argv
    py = sys.executable

    antes = count_by_source(os.path.join(HERE, "raw_listings.json"))

    # 1) coleta
    run([py, "scrape.py"])
    depois = count_by_source(os.path.join(HERE, "raw_listings.json"))

    # valida saude da coleta (detecta portal quebrado)
    problemas = [s for s, m in MIN_ESPERADO.items() if depois.get(s, 0) < m]
    print("\n=== coleta por fonte ===")
    for s in sorted(set(list(antes) + list(depois))):
        print(f"  {s}: {antes.get(s,0)} -> {depois.get(s,0)}")
    if problemas:
        raise SystemExit(
            f"ERRO: coleta abaixo do esperado em {problemas} — algum portal pode ter "
            f"mudado de estrutura. Verifique scrape.py antes de publicar."
        )

    # 2) gera o mapa
    run([py, "build.py"])

    if not push:
        print("\nOK (sem publicar, --no-push).")
        return

    # 3) publica
    hoje = datetime.date.today().isoformat()
    total = sum(depois.values())

    # detecta se os DADOS mudaram (antes de escrever o heartbeat)
    data_changed = subprocess.run(
        ["git", "diff", "--quiet", "--", "index.html", "raw_listings.json"],
        cwd=HERE).returncode != 0

    # batimento: prova de que a atualizacao rodou com sucesso (o vigia le isso)
    with open(os.path.join(HERE, "last_run.txt"), "w", encoding="utf-8") as f:
        f.write(f"{hoje} — {total} anuncios coletados "
                f"(dfimoveis {depois.get('dfimoveis',0)}, wimoveis {depois.get('wimoveis',0)})\n")

    run(["git", "add", "-A"])
    msg = (f"Atualiza dados ({hoje}) — {total} anuncios"
           if data_changed else f"Heartbeat {hoje} (sem mudanca nos anuncios)")
    run(["git", "-c", "commit.gpgsign=false", "commit", "-m", msg])
    run(["git", "push"])
    print(f"\n{'Publicado (dados novos)' if data_changed else 'Heartbeat registrado'}!"
          f" O GitHub Pages reconstrói em ~1 min.")
    print("https://bruno3495.github.io/imoveis-asa-norte/")


if __name__ == "__main__":
    main()
