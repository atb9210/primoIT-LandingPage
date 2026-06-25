#!/usr/bin/env python3
"""
PrimoIT — Adapter catalogo fornitori → modello interno canonico.

Oggi: legge il file XLSX del fornitore "outclick" (IT - Listino prezzi per i
rivenditori) e lo normalizza nel NOSTRO schema interno, generando shop/catalog.js.

Domani (XML): basta aggiungere una funzione parse_<formato>() che ritorni la stessa
lista di dict normalizzati — il frontend resta invariato.

Uso:
    python3 shop/build_catalog.py
"""

import json
import os
import re
import zipfile
import datetime
import xml.etree.ElementTree as ET

# ── Config ───────────────────────────────────────────────────────────────────
SUPPLIER_ID = "outclick"
SUPPLIER_NAME = "Outclick"
SOURCE_XLSX = "/Users/macasraf/Desktop/Progetto Sito PrimoIT/Listini fornitori/IT - Listino prezzi per i rivenditori.xlsx"
OUT_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.js")

# Sheet → categoria canonica
CATEGORY_MAP = {
    "Laptop - Scatola aperta": "Laptop",
    "Laptop - Ricondizionati": "Laptop",
    "Computer - Scatola aperta": "Computer",
    "Computer - Ricondizionati": "Computer",
    "Monitor": "Monitor",
    "Tablet e smartphone": "Tablet & Smartphone",
}
# Le "Altre apparecchiature informatiche" → Accessori (match per prefisso)
def map_category(sheet_name):
    if sheet_name in CATEGORY_MAP:
        return CATEGORY_MAP[sheet_name]
    if sheet_name.lower().startswith("altre apparecchiature"):
        return "Accessori"
    return None  # foglio ignorato

KNOWN_BRANDS = [
    "Dell", "HP", "Lenovo", "Apple", "Gigabyte", "AOC", "Acer", "Asus",
    "Microsoft", "Samsung", "MSI", "Toshiba", "Fujitsu", "LG", "Huawei",
]

# ── Lettore XLSX minimale (zip + XML, niente openpyxl) ───────────────────────
def _ln(tag):
    return tag.split('}')[-1]

def read_xlsx_sheets(path):
    """Ritorna {sheet_name: [ [cellvalues...], ... ]}."""
    z = zipfile.ZipFile(path)
    names = z.namelist()
    sst = []
    if 'xl/sharedStrings.xml' in names:
        root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in root:
            sst.append(''.join((t.text or '') for t in si.iter() if _ln(t.tag) == 't'))
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    sheets = [(s.get('name'), s.get(RID)) for s in wb.iter() if _ln(s.tag) == 'sheet']
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    relmap = {r.get('Id'): r.get('Target') for r in rels}
    out = {}
    for name, rid in sheets:
        tgt = relmap.get(rid, '')
        cand = tgt if tgt.startswith('xl/') else ('xl/' + tgt.lstrip('/'))
        if cand not in names:
            cand = 'xl/worksheets/' + tgt.split('/')[-1]
        sroot = ET.fromstring(z.read(cand))
        rows = []
        for r in sroot.iter():
            if _ln(r.tag) != 'row':
                continue
            cells = []
            for c in r:
                if _ln(c.tag) != 'c':
                    continue
                t = c.get('t')
                v = None
                for ch in c:
                    if _ln(ch.tag) == 'v':
                        v = ch.text
                    elif _ln(ch.tag) == 'is':
                        v = ''.join((x.text or '') for x in ch.iter() if _ln(x.tag) == 't')
                if t == 's' and v is not None:
                    try:
                        v = sst[int(v)]
                    except (ValueError, IndexError):
                        pass
                cells.append(v)
            rows.append(cells)
        out[name] = rows
    return out

# ── Helpers di normalizzazione ───────────────────────────────────────────────
def clean_text(s):
    if s is None:
        return ""
    s = str(s).replace('\xa0', ' ')
    s = re.sub(r'<[^>]+>', ' ', s)          # via tag HTML
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def parse_brand(title):
    t = title or ""
    for b in KNOWN_BRANDS:
        if re.search(r'\b' + re.escape(b) + r'\b', t, re.IGNORECASE):
            return "AOC" if b.upper() == "AOC" else b
    return "Altro"

def parse_condition_grade(qualita):
    q = (qualita or "").strip()
    low = q.lower()
    if "scatola aperta" in low or low.startswith("outlet"):
        return "Open Box", "A+"  # open box ≈ nuovo → trattato come A+
    if "nuovo" in low:
        return "Ricondizionato", "A+"
    m = re.search(r'A\+|A-|B\+|B-|C\+|C-|A\b|B\b|C\b', q)
    grade = m.group(0) if m else "—"
    return "Ricondizionato", grade

def parse_cpu(desc):
    d = desc or ""
    pats = [
        r'(Intel\s+)?Core\s*Ultra\s*\d+\s*[\w-]+',
        r'(Intel\s+)?Core[™\s]*i[3579][\w-]*\s*\d{3,5}[A-Z]*',
        r'i[3579][- ]\d{3,5}[A-Z]*',
        r'(AMD\s+)?Ryzen[™\s]*[\w ]*\d{3,5}[A-Z]*',
        r'\bN\d{3}\b',
        r'Apple\s+M\d[\w ]*',
    ]
    for p in pats:
        m = re.search(p, d, re.IGNORECASE)
        if m:
            return re.sub(r'\s+', ' ', m.group(0)).strip()
    return ""

def parse_ram(desc):
    d = desc or ""
    m = re.search(r'(\d{1,3})\s*GB\s*(?:DDR|RAM|LPDDR)', d, re.IGNORECASE)  # "16 GB DDR/RAM"
    if m:
        return m.group(1) + "GB"
    m = re.search(r'RAM\s*(\d{1,3})\s*GB', d, re.IGNORECASE)                # "RAM 16 GB"
    if m:
        return m.group(1) + "GB"
    return ""

def parse_drive(desc):
    d = desc or ""
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(TB|GB)\s*(SSD|NVMe|HDD|eMMC)', d, re.IGNORECASE)
    if m:
        return f"{m.group(1)}{m.group(2).upper()} {m.group(3).upper()}"
    m = re.search(r'(SSD|NVMe|HDD|eMMC)\s*(\d+(?:[.,]\d+)?)\s*(TB|GB)', d, re.IGNORECASE)  # "SSD 512 GB"
    if m:
        return f"{m.group(2)}{m.group(3).upper()} {m.group(1).upper()}"
    # tablet/smartphone: "128 GB UFS/Onboard/ROM" (GB seguito subito dal tipo → non è RAM)
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(TB|GB)\s+(UFS|ROM|Flash|Onboard)', d, re.IGNORECASE)
    if m:
        typ = m.group(3).lower()
        suffix = " UFS" if typ == "ufs" else (" ROM" if typ == "rom" else "")
        return f"{m.group(1)}{m.group(2).upper()}{suffix}"
    return ""

# GPU dedicate (workstation/gaming) vs integrate
GPU_DEDICATED = re.compile(
    r'(GeForce\s*RTX\s*\d{3,4}(?:\s*Ti)?|GeForce\s*GTX\s*\d{3,4}(?:\s*Ti)?'
    r'|RTX\s*\d{3,4}(?:\s*Ti)?|GTX\s*\d{3,4}(?:\s*Ti)?'
    r'|Quadro\s*[A-Z]?\d{3,4}\w*|\bMX\s?\d{3}\b'
    r'|Radeon\s*RX\s?\w+|Radeon\s*Pro\s?\w+)', re.IGNORECASE)
GPU_INTEGRATED = re.compile(
    r'(Iris\s*Xe|Iris\s*Plus|Arc\s*Graphics|UHD\s*Graphics\s*\d*'
    r'|HD\s*Graphics\s*\d*|Intel\s*Graphics|Radeon\s*\d{3,4}M?\s*Graphics'
    r'|Radeon\s*Vega\s*\d*|Radeon\s*Graphics)', re.IGNORECASE)

def parse_gpu(desc, cpu):
    """Ritorna (nome, vram, tipo); tipo in {'Dedicata','Integrata'}."""
    d = re.sub(r'[™®©]', ' ', desc or "")  # i simboli TM spezzano "RTX™ 5070"
    m = GPU_DEDICATED.search(d)
    if m:
        name = re.sub(r'\s+', ' ', m.group(0)).strip()
        if re.match(r'^(RTX|GTX)\b', name, re.IGNORECASE):
            name = "GeForce " + name  # RTX/GTX nudo → prefissa per chiarezza
        # VRAM: cerca "(8 GB GDDR6)" subito dopo il nome
        vm = re.search(r'(\d{1,2})\s*GB', d[m.end():m.end() + 30])
        vram = (vm.group(1) + "GB") if vm else ""
        return name, vram, "Dedicata"
    m = GPU_INTEGRATED.search(d)
    if m:
        return re.sub(r'\s+', ' ', m.group(0)).strip(), "", "Integrata"
    # fallback: deduci dalla CPU
    c = (cpu or "").lower()
    if "ryzen" in c:
        return "Radeon integrata", "", "Integrata"
    if "apple" in c or re.search(r'\bm[1-4]\b', c):
        return "GPU integrata", "", "Integrata"
    if "core" in c or re.search(r'\bi[3579]', c) or "intel" in c:
        return "Grafica Intel integrata", "", "Integrata"
    return "Integrata", "", "Integrata"

# Layout tastiera → codice breve
KB_TABLE = [
    (("swiss", "svizzer", "svicar"), "CH"),
    (("german", "tedesc", "deutsch", "nemšk", "deu"), "DE"),
    (("italian", "italiana", "tastiera ital"), "IT"),
    (("french", "frances", "franco", "fra"), "FR"),
    (("spanish", "spagnol", "špansk", "esp"), "ES"),
    (("nordic", "scandinav"), "SCA"),
    (("swedish", "svensk", "švedsk"), "SE"),
    (("danish", "dansk"), "DK"),
    (("norwegian", "norsk"), "NO"),
    (("finnish", "suomi"), "FI"),
    (("belgian", "belg"), "BE"),
    (("portug",), "PT"),
    (("arabic", "arab"), "AR"),
    (("united kingdom", "british", "uk keyboard"), "UK"),
    (("american", "usa", "u.s", "international"), "US"),
    (("english", "inglese", "angl"), "EN"),
    (("evro", "europ", "euro"), "EU"),
    (("straniera", "foreign", "stranih", "tuje", "priložen"), "INT"),
]

def kb_short(raw):
    s = (raw or "").strip().lower()
    if not s:
        return ""
    for keys, code in KB_TABLE:
        if any(k in s for k in keys):
            return code
    up = (raw or "").strip().upper()
    if 1 < len(up) <= 4 and up.isalpha():
        return up  # già un codice tipo "DEU"/"USA"
    return (raw or "").strip()[:6]

# Termini-tipo prodotto in sloveno → italiano (accessori e tablet)
SL_IT = [
    ("Napajalnik za prenosnik", "Alimentatore notebook"),
    ("Priklopna postaja", "Docking station"),
    ("Tablični računalnik", "Tablet"),
    ("Napajalnik", "Alimentatore"),
    ("Polnilnik", "Caricatore"),
    ("Tablica", "Tablet"),
    ("Prenosnik", "Notebook"),
    ("Tipkovnica", "Tastiera"),
    ("Tiskalnik", "Stampante"),
    ("Miška", "Mouse"),
    ("Zaslon", "Monitor"),
    ("Zvočnik", "Altoparlante"),
    ("Ohišje", "Case"),
]

def translate_title(t):
    """Traduce il termine-tipo iniziale se in sloveno; il resto (brand/modello) resta."""
    for sl, it in SL_IT:
        if t.lower().startswith(sl.lower()):
            return it + t[len(sl):]
    return t

def to_float(v):
    try:
        return round(float(str(v).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return None

def to_int(v):
    f = to_float(v)
    return int(f) if f is not None else 0

# ── Adapter outclick ─────────────────────────────────────────────────────────
def find_header_index(rows):
    for i, row in enumerate(rows[:8]):
        joined = [clean_text(c).lower() for c in row]
        if "qualità" in joined and "codice" in joined and "titolo" in joined:
            return i
    return None

def col_map(header):
    """Mappa nome colonna → indice."""
    m = {}
    for idx, c in enumerate(header):
        key = clean_text(c).lower()
        if key:
            m[key] = idx
    return m

def get(row, idx):
    return row[idx] if idx is not None and idx < len(row) else None

def normalize_outclick(sheets):
    products = []
    seen_ids = set()
    counts = {}
    for sheet_name, rows in sheets.items():
        category = map_category(sheet_name)
        if not category:
            continue
        h = find_header_index(rows)
        if h is None:
            continue
        cm = col_map(rows[h])
        c_qual = cm.get("qualità")
        c_code = cm.get("codice")
        c_qty = cm.get("qtà.") or cm.get("qtà") or cm.get("qta.")
        c_title = cm.get("titolo")
        c_desc = cm.get("descrizione")
        c_stock = cm.get("scorta")
        c_price = cm.get("prezzo per il rivenditore")
        c_kb = cm.get("layout della tastiera")
        for row in rows[h + 1:]:
            code = clean_text(get(row, c_code))
            title = clean_text(get(row, c_title))
            if not code or not title:
                continue  # riga vuota / separatore
            desc = clean_text(get(row, c_desc))
            spec_src = desc + " ｜ " + title  # titolo spesso contiene "/ i5 / RAM 16 GB"
            title = translate_title(title)    # IT per termini sloveni (accessori/tablet)
            condition, grade = parse_condition_grade(get(row, c_qual))
            pid = code
            if pid in seen_ids:
                pid = f"{code}-{len(products)}"
            seen_ids.add(pid)
            cpu_val = parse_cpu(spec_src)
            if category in ("Laptop", "Computer"):
                gpu_name, gpu_vram, gpu_type = parse_gpu(spec_src, cpu_val)
            else:
                gpu_name, gpu_vram, gpu_type = "", "", ""
            products.append({
                "id": pid,
                "supplier": SUPPLIER_ID,
                "category": category,
                "condition": condition,
                "grade": grade,
                "brand": parse_brand(title),
                "title": title,
                "cpu": cpu_val,
                "ram": parse_ram(spec_src),
                "drive": parse_drive(spec_src),
                "gpu": gpu_name,
                "gpu_vram": gpu_vram,
                "gpu_type": gpu_type,
                "keyboard": clean_text(get(row, c_kb)),
                "keyboard_short": kb_short(clean_text(get(row, c_kb))),
                "stock": to_int(get(row, c_qty)),
                "availability": clean_text(get(row, c_stock)) or "Disponibile",
                "price": to_float(get(row, c_price)),
                "description": desc,
            })
            counts[category] = counts.get(category, 0) + 1
    return products, counts

# ── Build ────────────────────────────────────────────────────────────────────
def build_meta(products):
    def uniq(field, order=None):
        vals = sorted({p[field] for p in products if p[field]})
        if order:
            vals = [v for v in order if v in vals] + [v for v in vals if v not in order]
        return vals
    return {
        "suppliers": [{"id": SUPPLIER_ID, "name": SUPPLIER_NAME}],
        "categories": uniq("category"),
        "conditions": uniq("condition"),
        "grades": uniq("grade", order=["A+", "A", "A-", "B", "C", "—"]),
        "gpuTypes": uniq("gpu_type", order=["Dedicata", "Integrata"]),
        "brands": uniq("brand"),
        "count": len(products),
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
    }

def main():
    print(f"→ Leggo: {SOURCE_XLSX}")
    sheets = read_xlsx_sheets(SOURCE_XLSX)
    products, counts = normalize_outclick(sheets)
    meta = build_meta(products)

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("/* GENERATO da build_catalog.py — non modificare a mano */\n")
        f.write("window.CATALOG_META = ")
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write(";\n")
        f.write("window.CATALOG = ")
        json.dump(products, f, ensure_ascii=False, indent=1)
        f.write(";\n")

    print(f"✓ Scritto {OUT_JS}")
    print(f"✓ Prodotti totali: {len(products)}")
    for cat in sorted(counts):
        print(f"   - {cat}: {counts[cat]}")
    print(f"✓ Brand: {', '.join(meta['brands'])}")
    print(f"✓ Gradi: {', '.join(meta['grades'])}  |  Condizioni: {', '.join(meta['conditions'])}")

if __name__ == "__main__":
    main()
