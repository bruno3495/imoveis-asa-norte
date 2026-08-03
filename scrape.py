# -*- coding: utf-8 -*-
"""
Scraper de imoveis (aluguel + venda) no DF — apartamentos e casas, 1-3 quartos.
Fontes: dfimoveis.com.br e wimoveis.com.br
Regioes: Asa Norte, Asa Sul, Jardim Botanico, Sobradinho, Grande Colorado,
         Guara I, Aguas Claras, Taguatinga.
Saida: raw_listings.json  (lista normalizada, ainda SEM deduplicar)
"""
import json, re, time, sys, gzip, unicodedata, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

BEDROOMS = (1, 2, 3)
DF_TYPES = ("apartamento", "casa")
DELAY = 0.35
MAX_PAGES = 200

# df:  caminho em /{op}/df/{df}/{tipo}/{n}-quartos
# wi:  caminho em /{op}/imoveis/df/{wi}?bedroom=n,n&page=N
# tokens: nomes de localidade aceitos no wimoveis (evita contaminacao quando o
#         site cai no fallback da cidade inteira)
REGIONS = [
    {"key": "asa-norte",       "label": "Asa Norte",
     "df": "brasilia/asa-norte",       "wi": "brasilia/asa-norte",
     "tokens": ["asa norte"]},
    {"key": "asa-sul",         "label": "Asa Sul",
     "df": "brasilia/asa-sul",         "wi": "brasilia/asa-sul",
     "tokens": ["asa sul"]},
    {"key": "jardim-botanico", "label": "Jardim Botânico",
     "df": "brasilia/jardim-botanico", "wi": "brasilia/setor-habitacional-jardim-botanico",
     "tokens": ["jardim botanico"]},
    {"key": "sobradinho",      "label": "Sobradinho",
     "df": "sobradinho/sobradinho",    "wi": "sobradinho",
     "tokens": ["sobradinho", "boa vista", "fercal", "nova colina"]},
    {"key": "grande-colorado", "label": "Grande Colorado",
     "df": "sobradinho/grande-colorado", "wi": "sobradinho/grande-colorado",
     "tokens": ["colorado"]},
    {"key": "guara-i",         "label": "Guará I",
     "df": "guara/guara-i",            "wi": "guara/guara-i",
     "tokens": ["guara i", "guara 1"]},
    {"key": "aguas-claras",    "label": "Águas Claras",
     "df": "aguas-claras",             "wi": "aguas-claras",
     "tokens": ["aguas", "arniqueiras"]},
    {"key": "taguatinga",      "label": "Taguatinga",
     "df": "taguatinga",               "wi": "taguatinga",
     "tokens": ["taguatinga", "vereda"]},
]


def norm(s):
    """minusculo, sem acento — p/ comparar nomes de localidade."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# -------------------------------------------------------------------- HTTP
def fetch(url, tries=3, timeout=30):
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept-Language": "pt-BR,pt;q=0.9",
                "Accept-Encoding": "gzip",
                "Accept": "text/html,application/xhtml+xml",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except Exception as e:
            print(f"    ! tentativa {attempt}/{tries} falhou ({e})", file=sys.stderr)
            time.sleep(1.5 * attempt)
    return None


def num(v):
    try:
        return float(v)
    except Exception:
        return None


# -------------------------------------------------------------- DFIMOVEIS
def parse_dfimoveis(html_bytes, operation, region, kind):
    """Extrai o ld+json ItemList. Retorna (itens, qtd_bruta_no_ItemList)."""
    html = html_bytes.decode("latin-1", errors="ignore")
    out, raw_count = [], 0
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            d = json.loads(block)
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("@type") != "ItemList":
            continue
        elems = d.get("itemListElement", [])
        raw_count += len(elems)
        for el in elems:
            it = el.get("item", {})
            offer = it.get("offers", {}) or {}
            g = it.get("geo", {}) or {}
            lat, lon = num(g.get("latitude")), num(g.get("longitude"))
            price = num(offer.get("price"))
            if lat is None or lon is None or not price:
                continue
            fs = it.get("floorSize", {}) or {}
            addr = it.get("address", {}) or {}
            out.append({
                "source": "dfimoveis",
                "id": str(it.get("identifier") or offer.get("url", "")),
                "region": region["key"],
                "operation": operation,
                "kind": kind,                      # apartamento | casa
                "title": (it.get("name") or "").strip(),
                "url": offer.get("url") or it.get("url"),
                "price": price,
                "condo": None,
                "bedrooms": it.get("numberOfBedrooms"),
                "bathrooms": None,
                "parking": None,
                "area": num(fs.get("value")),
                "lat": lat, "lon": lon,
                "address": (addr.get("streetAddress") or "").strip(),
                "image": (it.get("image") or [None])[0],
            })
    return out, raw_count


def scrape_dfimoveis(region, operation, seen):
    total = []
    for kind in DF_TYPES:
        for bed in BEDROOMS:
            base = (f"https://www.dfimoveis.com.br/{operation}/df/"
                    f"{region['df']}/{kind}/{bed}-quartos")
            for page in range(1, MAX_PAGES + 1):
                url = base if page == 1 else f"{base}?pagina={page}"
                b = fetch(url)
                if not b:
                    break
                items, raw = parse_dfimoveis(b, operation, region, kind)
                fresh = [x for x in items if (x["source"], x["id"]) not in seen]
                for x in fresh:
                    seen.add((x["source"], x["id"]))
                total.extend(fresh)
                if page == 1 or len(fresh):
                    print(f"    df {region['key']:16s} {operation:7s} {kind:11s} "
                          f"{bed}q p{page:<3d} raw={raw:2d} novos={len(fresh)}")
                if raw < 30:
                    break
                time.sleep(DELAY)
    return total


# --------------------------------------------------------------- WIMOVEIS
def parse_wimoveis(html_bytes, want_operation, region):
    html = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*)', html, re.S)
    if not m:
        return [], 0, 0
    try:
        obj, _ = json.JSONDecoder().raw_decode(m.group(1))
    except Exception:
        return [], 0, 0
    ls = obj.get("listStore", {})
    total_pages = ls.get("paging", {}).get("totalPages", 0)
    postings = ls.get("listPostings", []) or []
    out, rejeitados = [], 0
    for p in postings:
        loc = p.get("postingLocation", {}) or {}
        locname = norm(((loc.get("location") or {}).get("name")))
        # descarta contaminacao de bairro vizinho (fallback do site)
        if not any(t in locname for t in region["tokens"]):
            rejeitados += 1
            continue
        geo = ((loc.get("postingGeolocation") or {}).get("geolocation")) or {}
        lat, lon = num(geo.get("latitude")), num(geo.get("longitude"))
        if lat is None or lon is None:
            continue
        price, op = None, None
        for pot in p.get("priceOperationTypes", []) or []:
            opname = (pot.get("operationType", {}) or {}).get("name", "").lower()
            op_norm = ("venda" if "venda" in opname
                       else "aluguel" if ("aluguel" in opname or "loca" in opname) else None)
            prices = pot.get("prices") or []
            amt = num(prices[0].get("amount")) if prices else None
            if op_norm == want_operation and amt:
                price, op = amt, op_norm
                break
        if not price:
            continue
        feats = p.get("mainFeatures", {}) or {}
        beds = baths = parking = area = None
        for fid, f in feats.items():
            label = (f.get("label") or "").lower()
            val = f.get("value")
            vnum = num(re.sub(r"[^\d.]", "", str(val))) if val is not None else None
            if fid == "CFT2" or "quarto" in label or "dormit" in label:
                beds = int(vnum) if vnum else beds
            elif fid == "CFT3" or "banheiro" in label:
                baths = int(vnum) if vnum else baths
            elif fid == "CFT7" or "vaga" in label or "garag" in label:
                parking = int(vnum) if vnum else parking
            elif fid in ("CFT101", "CFT100"):
                if area is None and vnum:
                    area = vnum
        rtype = norm((p.get("realEstateType", {}) or {}).get("name", ""))
        kind = ("casa" if "casa" in rtype or "sobrado" in rtype
                else "apartamento" if "apart" in rtype or "kitnet" in rtype or "flat" in rtype
                else "outro")
        exp = p.get("expenses") or {}
        pics = (p.get("visiblePictures") or {}).get("pictures") or []
        img = None
        if pics:
            pic = pics[0]
            img = pic.get("url730x532") or next((v for k, v in pic.items() if str(k).startswith("url")), None)
        rel = p.get("url", "")
        out.append({
            "source": "wimoveis",
            "id": str(p.get("postingId")),
            "region": region["key"],
            "operation": op,
            "kind": kind,
            "title": (p.get("title") or p.get("generatedTitle") or "").strip(),
            "url": ("https://www.wimoveis.com.br" + rel) if rel.startswith("/") else rel,
            "price": price,
            "condo": num(exp.get("amount")),
            "bedrooms": beds,
            "bathrooms": baths,
            "parking": parking,
            "area": area,
            "lat": lat, "lon": lon,
            "address": ((loc.get("address") or {}).get("name") or "").strip(),
            "image": img,
        })
    return out, total_pages, rejeitados


def scrape_wimoveis(region, operation, seen):
    total = []
    for bed in BEDROOMS:
        base = f"https://www.wimoveis.com.br/{operation}/imoveis/df/{region['wi']}"
        total_pages = None
        for page in range(1, MAX_PAGES + 1):
            url = f"{base}?bedroom={bed},{bed}" + (f"&page={page}" if page > 1 else "")
            b = fetch(url)
            if not b:
                break
            items, tp, rej = parse_wimoveis(b, operation, region)
            if total_pages is None:
                total_pages = tp
            fresh = [x for x in items if (x["source"], x["id"]) not in seen]
            for x in fresh:
                seen.add((x["source"], x["id"]))
            total.extend(fresh)
            if page == 1 or len(fresh):
                print(f"    wi {region['key']:16s} {operation:7s} {bed}q "
                      f"p{page:<3d}/{total_pages or '?'} novos={len(fresh)} fora_regiao={rej}")
            if total_pages and page >= total_pages:
                break
            if not tp:
                break
            time.sleep(DELAY)
    return total


# ------------------------------------------------------------------- MAIN
def keep_bedrooms(x):
    try:
        b = int(x.get("bedrooms"))
    except (TypeError, ValueError):
        return False
    x["bedrooms"] = b
    return b in BEDROOMS


def main():
    only = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    regions = [r for r in REGIONS if not only or r["key"] == only]
    listings, seen = [], set()
    t0 = time.time()
    for r in regions:
        print(f"\n=== {r['label']} ===")
        for op in ("venda", "aluguel"):
            listings += scrape_dfimoveis(r, op, seen)
            listings += scrape_wimoveis(r, op, seen)
        print(f"  -> acumulado: {len(listings)} anuncios "
              f"({(time.time()-t0)/60:.1f} min)")

    before = len(listings)
    listings = [x for x in listings if keep_bedrooms(x)]
    print(f"\nColetados: {before} | apos filtro 1-3 quartos: {len(listings)}")

    with open("raw_listings.json", "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> raw_listings.json salvo ({(time.time()-t0)/60:.1f} min no total)")


if __name__ == "__main__":
    main()
