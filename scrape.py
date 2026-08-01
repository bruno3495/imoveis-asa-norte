# -*- coding: utf-8 -*-
"""
Scraper de imoveis (aluguel + venda) na Asa Norte - Brasilia/DF
Fontes: dfimoveis.com.br e wimoveis.com.br
Filtro: 1, 2 ou 3 quartos.
Saida: raw_listings.json  (lista normalizada, ainda SEM deduplicar)
"""
import json, re, time, sys, gzip, io, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

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

# -------------------------------------------------------------- DFIMOVEIS
def num(v):
    try: return float(v)
    except Exception: return None

def parse_dfimoveis(html_bytes, operation):
    """html decodificado em latin-1; extrai ld+json ItemList.
    Retorna (items_normalizados, qtd_bruta_no_ItemList)."""
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
            geo = it.get("offers", {}) or {}
            g = it.get("geo", {}) or {}
            lat, lon = num(g.get("latitude")), num(g.get("longitude"))
            if lat is None or lon is None:
                continue
            price = num(geo.get("price"))
            if not price:
                continue
            fs = it.get("floorSize", {}) or {}
            addr = it.get("address", {}) or {}
            out.append({
                "source": "dfimoveis",
                "id": str(it.get("identifier") or geo.get("url", "")),
                "operation": operation,
                "type": (it.get("@type", ["", ""])[-1] if isinstance(it.get("@type"), list) else str(it.get("@type"))),
                "title": (it.get("name") or "").strip(),
                "url": geo.get("url") or it.get("url"),
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

def scrape_dfimoveis(operation, max_pages=90, delay=0.4):
    base = f"https://www.dfimoveis.com.br/{operation}/df/brasilia/asa-norte/apartamento"
    all_items, seen_ids = [], set()
    for page in range(1, max_pages + 1):
        url = base if page == 1 else f"{base}?pagina={page}"
        b = fetch(url)
        if not b:
            break
        items, raw_count = parse_dfimoveis(b, "venda" if operation == "venda" else "aluguel")
        fresh = [x for x in items if x["id"] not in seen_ids]
        for x in fresh:
            seen_ids.add(x["id"])
        print(f"  dfimoveis {operation} p{page}: {raw_count} no ItemList / {len(fresh)} novos validos")
        all_items.extend(fresh)
        if raw_count < 30 or not fresh:      # ultima pagina (ItemList incompleto)
            break
        time.sleep(delay)
    return all_items

# --------------------------------------------------------------- WIMOVEIS
def parse_wimoveis(html_bytes, want_operation):
    html = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*)', html, re.S)
    if not m:
        return [], 0
    try:
        obj, _ = json.JSONDecoder().raw_decode(m.group(1))
    except Exception:
        return [], 0
    ls = obj.get("listStore", {})
    total_pages = ls.get("paging", {}).get("totalPages", 0)
    out = []
    for p in ls.get("listPostings", []) or []:
        loc = p.get("postingLocation", {}) or {}
        geo = ((loc.get("postingGeolocation") or {}).get("geolocation")) or {}
        lat, lon = num(geo.get("latitude")), num(geo.get("longitude"))
        if lat is None or lon is None:
            continue
        # preco + operacao
        price, op = None, None
        for pot in p.get("priceOperationTypes", []) or []:
            opname = (pot.get("operationType", {}) or {}).get("name", "").lower()
            op_norm = "venda" if "venda" in opname else ("aluguel" if ("aluguel" in opname or "loca" in opname) else None)
            prices = pot.get("prices") or []
            amt = num(prices[0].get("amount")) if prices else None
            if op_norm == want_operation and amt:
                price, op = amt, op_norm
                break
        if not price:
            continue
        # features
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
            elif fid in ("CFT101", "CFT100") or "til" in label or "total" in label:
                if area is None and vnum:
                    area = vnum
        exp = p.get("expenses") or {}
        pics = (p.get("visiblePictures") or {}).get("pictures") or []
        img = None
        if pics:
            pic = pics[0]
            img = pic.get("url730x532") or pic.get("url") or next((v for k, v in pic.items() if str(k).startswith("url")), None)
        rel = p.get("url", "")
        out.append({
            "source": "wimoveis",
            "id": str(p.get("postingId")),
            "operation": op,
            "type": (p.get("realEstateType", {}) or {}).get("name", ""),
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
    return out, total_pages

def scrape_wimoveis(operation, max_pages=40, delay=0.4):
    """Filtra por quartos via ?bedroom=N,N e pagina via &page=N."""
    base = f"https://www.wimoveis.com.br/{operation}/imoveis/df/brasilia/asa-norte"
    all_items, seen_ids = [], set()
    for bed in (1, 2, 3):
        total_pages = None
        for page in range(1, max_pages + 1):
            url = f"{base}?bedroom={bed},{bed}" + (f"&page={page}" if page > 1 else "")
            b = fetch(url)
            if not b:
                break
            items, tp = parse_wimoveis(b, operation)
            if total_pages is None:
                total_pages = tp
            fresh = [x for x in items if x["id"] not in seen_ids]
            for x in fresh:
                seen_ids.add(x["id"])
            print(f"  wimoveis {operation} {bed}q p{page}/{total_pages}: {len(items)} itens ({len(fresh)} novos)")
            all_items.extend(fresh)
            if not fresh or (total_pages and page >= total_pages):
                break
            time.sleep(delay)
    return all_items

# ------------------------------------------------------------------- MAIN
def keep_bedrooms(x):
    b = x.get("bedrooms")
    try:
        b = int(b)
    except (TypeError, ValueError):
        return False
    x["bedrooms"] = b
    return b in (1, 2, 3)

def main():
    listings = []
    print("== dfimoveis ==")
    listings += scrape_dfimoveis("venda")
    listings += scrape_dfimoveis("aluguel")
    print("== wimoveis ==")
    listings += scrape_wimoveis("venda")
    listings += scrape_wimoveis("aluguel")

    before = len(listings)
    listings = [x for x in listings if keep_bedrooms(x)]
    print(f"\nColetados: {before} | apos filtro 1-3 quartos: {len(listings)}")

    with open("raw_listings.json", "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=1)
    print("-> raw_listings.json salvo")

if __name__ == "__main__":
    main()
