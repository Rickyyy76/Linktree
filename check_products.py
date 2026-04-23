#!/usr/bin/env python3
"""
Checkt ob alle ASC-Produkte noch verfügbar sind.
Entfernt nicht mehr existierende Produkte aus index.html.
"""
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

INDEX_FILE = "index.html"
TIMEOUT = 15
MAX_WORKERS = 8  # Parallele Requests (nicht zu hoch, sonst blockt ASC)

# Headers um wie ein normaler Browser zu wirken
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def check_url(url):
    """Returns (url, is_available, reason)."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        
        # 404 oder andere Error-Codes
        if r.status_code >= 400:
            return (url, False, f"HTTP {r.status_code}")
        
        # Text auf "Out of stock" / "not found" checken
        text_lower = r.text.lower()
        
        # Produkt-Seite leitet auf Homepage weiter = Produkt weg
        if "/catalog/product" not in r.url and "amsterdamseedcenter.com/en/" == r.url.rstrip("/") + "/":
            return (url, False, "redirected to homepage")
        
        # Eindeutige "not found" Indikatoren
        if "whoops, our bad" in text_lower or "page not found" in text_lower:
            return (url, False, "not found page")
        
        # "Out of Stock" - nur wenn EXPLIZIT im Verfügbarkeits-Block erwähnt
        # Nicht jedes Vorkommen im Text (könnte z.B. ein Review sein)
        if re.search(r'"availability"\s*:\s*"[^"]*outofstock', text_lower) or \
           re.search(r'class="[^"]*out-of-stock', text_lower) or \
           "this product is currently not available" in text_lower:
            return (url, False, "out of stock")
        
        return (url, True, "ok")
    
    except requests.RequestException as e:
        # Bei Netzwerkfehler: nicht entfernen (vorsichtig sein)
        return (url, True, f"error: {e} (kept)")

def main():
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    
    # Finde alle Produkt-URLs aus der products-Array
    # Muster: url: B + "xxx" + A
    # Das sind alle Produkte die auf ASC verweisen
    url_pattern = r'url:B\+"([^"]+)"\+A'
    matches = list(re.finditer(url_pattern, html))
    
    if not matches:
        print("Keine Produkt-URLs gefunden!")
        return
    
    # Baue vollständige URLs
    base = "https://www.amsterdamseedcenter.com/en/"
    aff = "?affiliate_code=CPrOZdqBHg&referring_service=widget"
    products = []
    for m in matches:
        path = m.group(1)
        full_url = base + path + aff
        products.append((m, path, full_url))
    
    print(f"Checking {len(products)} Produkte...")
    print("=" * 60)
    
    dead = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_product = {
            executor.submit(check_url, p[2]): p 
            for p in products
        }
        
        checked = 0
        for future in as_completed(future_to_product):
            product = future_to_product[future]
            url, available, reason = future.result()
            checked += 1
            
            if not available:
                dead.append(product)
                print(f"❌ [{checked}/{len(products)}] {product[1][:60]} — {reason}")
            else:
                if checked % 20 == 0:
                    print(f"✓  {checked}/{len(products)} geprüft...")
    
    print("=" * 60)
    print(f"Fertig: {len(dead)} von {len(products)} Produkten nicht verfügbar")
    
    if not dead:
        print("✓ Alle Produkte OK, keine Änderungen nötig")
        return
    
    # Entferne tote Produkte aus HTML
    # Finde die komplette Zeile des Produkts und entferne sie
    new_html = html
    for match, path, url in dead:
        # Finde die Zeile die diese URL enthält
        # Produkt-Zeile sieht so aus: {cat:"...",name:"...",price:"...",img:C+"...",url:B+"path"+A},
        line_pattern = re.compile(
            r'  \{cat:"[^"]+",name:"[^"]+",price:"[^"]+",img:[^,]+,url:B\+"' 
            + re.escape(path) 
            + r'"\+A\},\n',
            re.MULTILINE
        )
        new_html, n_removed = line_pattern.subn("", new_html)
        if n_removed == 0:
            print(f"⚠️  Zeile für {path} nicht gefunden (evtl. schon entfernt)")
    
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)
    
    print(f"\n✓ {len(dead)} Produkte entfernt. index.html aktualisiert.")

if __name__ == "__main__":
    main()