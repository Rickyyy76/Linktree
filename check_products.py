#!/usr/bin/env python3
"""
Checkt ob alle ASC-Produkte in products.txt noch verfügbar sind.
Entfernt nicht mehr existierende Produkt-Blöcke aus products.txt.

products.txt enthält den rohen Widget-HTML-Dump von Amsterdam Seed Center.
Format: <div class="widget-product">...</div> pro Produkt.
"""
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

PRODUCTS_FILE = "products.txt"
TIMEOUT = 15
MAX_WORKERS = 8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def check_url(url):
    """Returns (url, is_available, reason)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)

        if r.status_code >= 400:
            return (url, False, f"HTTP {r.status_code}")

        text_lower = r.text.lower()

        # Produkt-Seite leitet auf Homepage weiter = Produkt weg
        if "/catalog/product" not in r.url and "amsterdamseedcenter.com/en/" == r.url.rstrip("/") + "/":
            return (url, False, "redirected to homepage")

        if "whoops, our bad" in text_lower or "page not found" in text_lower:
            return (url, False, "not found page")

        if re.search(r'"availability"\s*:\s*"[^"]*outofstock', text_lower) or \
           re.search(r'class="[^"]*out-of-stock', text_lower) or \
           "this product is currently not available" in text_lower:
            return (url, False, "out of stock")

        return (url, True, "ok")

    except requests.RequestException as e:
        # Bei Netzwerkfehler: vorsichtig sein und NICHT entfernen
        return (url, True, f"error: {e} (kept)")


def extract_products(html):
    """
    Zerlegt den Widget-HTML in einzelne Produkt-Blöcke.
    Returns: Liste von (block_text, url) Tuples.
    """
    # Teile am <div class="widget-product" — jeder nachfolgende Teil ist ein Produkt
    parts = html.split('<div class="widget-product"')
    products = []

    # parts[0] ist der Header (vor dem ersten widget-product), den behalten wir
    header = parts[0]

    for part in parts[1:]:
        # Rekonstruiere vollständigen Block
        block = '<div class="widget-product"' + part
        # Den Block schneiden wir beim nächsten </div></div> ab (Ende eines Produkts)
        # Einfacher Weg: Wir halten das ganze "part" (wird beim Zusammensetzen wieder als Trenner benutzt)

        # Extrahiere URL
        url_match = re.search(r'href="([^"]+)"', part)
        if url_match:
            products.append((part, url_match.group(1)))
        else:
            products.append((part, None))

    return header, products


def main():
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    header, products = extract_products(html)

    # Filter: nur Produkte mit URL checken (Header/Promo-Items ohne URL bleiben erhalten)
    checkable = [(i, part, url) for i, (part, url) in enumerate(products) if url]

    print(f"Gefunden: {len(products)} Produkt-Blöcke, {len(checkable)} mit URL zu prüfen")
    print("=" * 60)

    dead_indices = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(check_url, url): (idx, url)
            for idx, _, url in checkable
        }

        checked = 0
        for future in as_completed(future_to_idx):
            idx, url = future_to_idx[future]
            _, available, reason = future.result()
            checked += 1

            if not available:
                dead_indices.add(idx)
                print(f"❌ [{checked}/{len(checkable)}] {url[:70]} — {reason}")
            else:
                if checked % 20 == 0:
                    print(f"✓  {checked}/{len(checkable)} geprüft...")

    print("=" * 60)
    print(f"Fertig: {len(dead_indices)} von {len(products)} Produkten nicht verfügbar")

    if not dead_indices:
        print("✓ Alle Produkte OK, keine Änderungen nötig")
        return

    # Baue neues HTML: behalte header + alle nicht-toten Produkte
    new_parts = [header]
    kept = 0
    for i, (part, _) in enumerate(products):
        if i not in dead_indices:
            new_parts.append('<div class="widget-product"' + part)
            kept += 1

    new_html = ''.join(new_parts)

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"\n✓ {len(dead_indices)} tote Produkte entfernt.")
    print(f"✓ {kept} verfügbare Produkte in {PRODUCTS_FILE} behalten.")


if __name__ == "__main__":
    main()