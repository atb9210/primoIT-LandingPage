#!/usr/bin/env python3
"""
PrimoIT — Adapter catalogo dal feed XML di OutletClick.

Sorgente ricca (foto reali, descrizioni IT, specifiche strutturate, EAN, prezzo,
grado/condizione) → modello interno canonico → shop/catalog.js.

Sostituisce il vecchio build da xlsx: il feed XML ha molto di più ed è corretto
per la singola unità refurbished.

Uso:
    python3 shop/build_catalog_xml.py
"""
import json, os, re, html, urllib.request, datetime
import xml.etree.ElementTree as ET

FEED_URL = "https://outletclick.com/PoceniPCsync/it_outletclick.xml"
CACHE = "/tmp/outclick.xml"
OUT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.js")
SUPPLIER_ID = "outclick"

# ── helpers ──────────────────────────────────────────────────────────────────
def fetch_feed():
    try:
        print("Scarico il feed XML…")
        data = urllib.request.urlopen(FEED_URL, timeout=90).read()
        open(CACHE, "wb").write(data)
        return data
    except Exception as e:
        print(f"  download fallito ({e}); uso cache {CACHE}")
        return open(CACHE, "rb").read()

BRAND_MAP = {
    "hewlett packard": "HP", "hp inc.": "HP", "hp": "HP", "hp inc": "HP",
    "lenovo": "Lenovo", "dell": "Dell", "dell inc.": "Dell", "dell technologies": "Dell",
    "asus": "Asus", "asustek": "Asus", "acer": "Acer", "msi": "MSI", "micro-star": "MSI",
    "gigabyte": "Gigabyte", "fujitsu": "Fujitsu", "microsoft": "Microsoft", "apple": "Apple",
    "aoc": "AOC", "samsung": "Samsung", "lg": "LG", "toshiba": "Toshiba", "huawei": "Huawei",
    "drugo": "Altro", "": "Altro",
}
def norm_brand(m):
    m = (m or "").strip()
    return BRAND_MAP.get(m.lower(), m or "Altro")

def map_category(cats):
    c = (cats or "").lower()
    if "monitor" in c: return "Monitor"
    if "tablet" in c or "smartphone" in c: return "Tablet & Smartphone"
    if "laptop" in c or "notebook" in c or "portatili" in c: return "Laptop"
    if "computer" in c or "desktop" in c: return "Computer"
    return "Accessori"

def parse_grade(grade, condition):
    """Normalizza in 2 sole condizioni dal campo `grade` (il `product_condition` è sporco e si ignora).
    grade 'Scatola aperta'/'Odprta embalaža'/open -> Scatola aperta (A+);
    grade 'A/A-/B qualità' -> Ricondizionato (con la lettera del grado)."""
    g = (grade or "").lower()
    if "scatola aperta" in g or "open" in g or "odprta" in g or "embala" in g:
        return "A+", "Scatola aperta"
    m = re.search(r"(A\+|A-|B\+|B-|C\+|C-|A|B|C)", grade or "", re.I)
    return (m.group(1).upper() if m else "—"), "Ricondizionato"

DED = re.compile(r"(geforce|rtx|gtx|radeon rx|radeon pro|quadro|\barc\b|\bmx\d)", re.I)
def gpu_type(gc):
    if not gc: return ""
    return "Dedicata" if DED.search(gc) else "Integrata"

def clean_desc(h):
    """Da HTML doppio-escapato del feed a HTML pulito per il render (via innerHTML)."""
    if not h: return ""
    t = html.unescape(h)               # &amp;lt; -> &lt; -> <
    t = re.sub(r"<style[^>]*>.*?</style>", "", t, flags=re.S | re.I)
    t = re.sub(r"<script[^>]*>.*?</script>", "", t, flags=re.S | re.I)
    t = re.sub(r'\sdata-[a-z-]+="[^"]*"', "", t)   # togli attributi pagebuilder
    t = re.sub(r'\sclass="[^"]*"', "", t)
    t = re.sub(r'\sstyle="[^"]*"', "", t)          # togli stili inline (evita overflow/larghezze fisse)
    return t.strip()

def text(p, tag):
    e = p.find(tag); return (e.text or "").strip() if e is not None else ""

def inch_of(size):
    """'35,6 cm (14,0″)' -> '14″' (pollici puliti)."""
    m = re.search(r'\(([\d.,]+)\s*[″"\']', size or "") or re.search(r'([\d.,]+)\s*[″"\']', size or "")
    if not m:
        return ""
    n = m.group(1).replace(",", ".")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n + "″"

def res_short(res):
    """'FHD / 1920 x 1080' -> 'FHD'."""
    return (res or "").split("/")[0].strip()

def to_int(s):
    m = re.search(r"\d+", s or ""); return int(m.group()) if m else 0
def to_float(s):
    s = (s or "").replace(",", ".");
    m = re.search(r"\d+(\.\d+)?", s); return round(float(m.group()), 2) if m else None

# ── build ────────────────────────────────────────────────────────────────────
def build():
    root = ET.fromstring(fetch_feed())
    products = []
    for p in root:
        if p.tag != "product": continue
        sku = text(p, "sku"); name = text(p, "product_name")
        if not sku or not name: continue
        brand = norm_brand(text(p, "manufacturer"))
        category = map_category(text(p, "categories"))
        grade, condition = parse_grade(text(p, "grade"), text(p, "product_condition"))
        gc = text(p, "graphic_card")
        # immagini: image, image1..image10 (dedup mantenendo l'ordine)
        imgs = []
        for tag in ["image"] + [f"image{i}" for i in range(1, 11)]:
            u = text(p, tag)
            if u and u not in imgs: imgs.append(u)
        cpu = text(p, "processor_model") or text(p, "processor")
        drive = " ".join(x for x in [text(p, "disk"), text(p, "hdd_type")] if x).strip()
        screen = text(p, "screen_size") or text(p, "monitor_size")
        resolution = text(p, "monitor_max_resolution")
        panel = text(p, "display_type")
        inch = inch_of(screen)
        rs = res_short(resolution)
        screen_short = (inch + " · " + rs) if (inch and rs) else (inch or rs or screen)
        products.append({
            "id": sku,
            "supplier": SUPPLIER_ID,
            "ean": text(p, "ean"),
            "category": category,
            "brand": brand,
            "title": name,
            "cpu": cpu,
            "ram": text(p, "memory"),
            "ram_type": text(p, "ram_type"),
            "drive": drive,
            "gpu": gc,
            "gpu_type": gpu_type(gc),
            "gpu_vram": "",
            "screen": screen,
            "screen_short": screen_short,
            "resolution": resolution,
            "panel": panel,
            "os": text(p, "oper_system"),
            "grade": grade,
            "condition": condition,
            "warranty": to_int(text(p, "warranty_months")),
            "stock": to_int(text(p, "qty")),
            "availability": text(p, "availability") or "Disponibile",
            # price = NETTO (IVA escl.): coerente con carrello/preventivo/Stripe (+22%)
            "price": to_float(text(p, "price_without_vat")) or to_float(text(p, "price")),
            "price_incl": to_float(text(p, "price")),
            "image": imgs[0] if imgs else "",
            "images": imgs,
            "short_desc": text(p, "short_description"),
            "description": clean_desc(text(p, "description")),
            "energy_class": text(p, "energy_class"),
            "url": text(p, "url_path"),
        })

    # meta per i filtri
    def uniq(field, order=None):
        vals = sorted({p[field] for p in products if p.get(field)})
        if order: vals = [v for v in order if v in vals] + [v for v in vals if v not in order]
        return vals
    meta = {
        "suppliers": [{"id": SUPPLIER_ID, "name": "Outclick"}],
        "categories": uniq("category", ["Laptop", "Computer", "Monitor", "Tablet & Smartphone", "Accessori"]),
        "conditions": uniq("condition"),
        "grades": uniq("grade", ["A+", "A", "A-", "B", "C", "—"]),
        "gpuTypes": uniq("gpu_type", ["Dedicata", "Integrata"]),
        "brands": uniq("brand"),
        "count": len(products),
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("/* GENERATO da build_catalog_xml.py — non modificare a mano */\n")
        f.write("window.CATALOG_META = " + json.dumps(meta, ensure_ascii=False, indent=2) + ";\n")
        f.write("window.CATALOG = " + json.dumps(products, ensure_ascii=False, indent=1) + ";\n")
    print(f"✓ {len(products)} prodotti -> {OUT_JS}")
    print(f"✓ categorie: {meta['categories']}")
    print(f"✓ brand: {meta['brands']}")
    n_img = sum(1 for p in products if p['images'])
    n_ean = sum(1 for p in products if p['ean'])
    print(f"✓ con foto: {n_img}/{len(products)} · con EAN: {n_ean}/{len(products)}")

if __name__ == "__main__":
    build()
