"""
OpenStreetMap Lead Finder (bilkul free, koi API key ya card nahi)
-----------------------------------------------------------------
Aapke shehar ki dukaanein dhundta hai jinki website OpenStreetMap par
darj nahi hai, aur do file banata hai:
    leads.csv             -> Excel me kholne ke liye
    dashboard_import.json -> dashboard me "जोड़ो" se daalne ke liye

Setup:
    pip install requests
Run:
    python osm_lead_finder.py
"""

import csv
import json
import time
from pathlib import Path

import requests

# ---------------- CONFIG (yahan badlo) ----------------
CITY = "kanpur"            # shehar ka naam (Hindi ya English dono chalega)
CATEGORIES = ["boutique", "salon", "bakery"]   # niche ki list me se chuno
MAX_LEADS = 50
SEEN_FILE = Path("seen_osm.json")
# ------------------------------------------------------

# category -> OpenStreetMap tags
TAGS = {
    "boutique": [("shop", "boutique"), ("shop", "clothes"), ("shop", "tailor")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "bakery": [("shop", "bakery"), ("shop", "pastry"), ("shop", "confectionery")],
    "gym": [("leisure", "fitness_centre")],
    "restaurant": [("amenity", "restaurant"), ("amenity", "cafe")],
    "jewellery": [("shop", "jewelry")],
    "electronics": [("shop", "electronics"), ("shop", "mobile_phone")],
}

HEADERS = {"User-Agent": "lead-finder-personal-project/1.0"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"


def get_bbox(city):
    r = requests.get(
        NOMINATIM,
        params={"q": city, "format": "json", "limit": 1, "countrycodes": "in"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        raise SystemExit(f"'{city}' naam ka shehar nahi mila. Spelling check karo.")
    south, north, west, east = data[0]["boundingbox"]
    print("Mila:", data[0].get("display_name", city))
    return south, west, north, east


OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def run_query(query):
    """Server busy ho to doosre server par aur dobara try karta hai."""
    for attempt in range(3):
        for url in OVERPASS_URLS:
            try:
                r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=120)
                if r.status_code == 200:
                    return r.json().get("elements", [])
                print(f"  server busy ({r.status_code}), dobara try kar rahe hain...")
            except requests.RequestException as ex:
                print("  connection dikkat:", ex.__class__.__name__)
            time.sleep(5)
    return None


def fetch_places(bbox):
    s, w, n, e = bbox
    found = {}
    for cat in CATEGORIES:
        tag_list = TAGS.get(cat, [])
        if not tag_list:
            continue
        parts = "".join(
            f'nwr["{k}"="{v}"]["name"]({s},{w},{n},{e});' for k, v in tag_list
        )
        query = f"[out:json][timeout:60];({parts});out center tags;"
        print("Category:", cat)
        els = run_query(query)
        if els is None:
            print("  is category ko chhod rahe hain (server jawab nahi de raha).")
            continue
        print("  dukaanein mili:", len(els))
        for el in els:
            found[f"{el['type']}/{el['id']}"] = el
        time.sleep(15)
    return list(found.values())


def label_for(tags):
    for cat in CATEGORIES:
        for key, val in TAGS.get(cat, []):
            if tags.get(key) == val:
                return cat
    return ""


def clean_phone(tags):
    p = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or ""
    return p.split(";")[0].strip()


def has_website(tags):
    for k in ("website", "contact:website", "url"):
        v = tags.get(k, "").lower()
        if v and not any(s in v for s in ("instagram.com", "facebook.com", "fb.com")):
            return True
    return False


def social(tags, key):
    return (tags.get(f"contact:{key}") or tags.get(key) or "").strip()


def address(tags):
    keys = ["addr:housenumber", "addr:street", "addr:suburb", "addr:city"]
    return ", ".join(tags[k] for k in keys if tags.get(k))


def score(item):
    s = 0
    if item["phone"]:
        s += 3
    if item["ig"] or item["fb"]:
        s += 2
    if item["has_hours"]:
        s += 1
    return s


def main():
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    bbox = get_bbox(CITY)
    time.sleep(1)  # nominatim ka niyam: 1 request / second
    print("Dukaanein dhundh rahe hain... (1-2 minute lag sakte hain)")
    elements = fetch_places(bbox)

    items = []
    for el in elements:
        tags = el.get("tags", {})
        uid = f"{el['type']}/{el['id']}"
        if uid in seen or not tags.get("name") or has_website(tags):
            continue
        items.append({
            "uid": uid,
            "name": tags["name"],
            "cat": label_for(tags),
            "phone": clean_phone(tags),
            "ig": social(tags, "instagram"),
            "fb": social(tags, "facebook"),
            "addr": address(tags),
            "has_hours": bool(tags.get("opening_hours")),
        })

    items.sort(key=score, reverse=True)
    items = items[:MAX_LEADS]

    if not items:
        print("Koi nayi lead nahi mili. Dusra shehar ya category try karo.")
        return

    with open("leads.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["नाम", "कैटेगरी", "फोन", "Instagram", "Facebook", "पता"])
        for it in items:
            w.writerow([it["name"], it["cat"], it["phone"], it["ig"], it["fb"], it["addr"]])

    base = int(time.time() * 1000)
    dash = []
    for i, it in enumerate(items):
        dash.append({
            "id": base + i,
            "name": it["name"],
            "cat": it["cat"],
            "phone": it["phone"],
            "ig": it["ig"],
            "fb": it["fb"],
            "due": "",
            "notes": it["addr"],
            "status": "नई",
        })
    Path("dashboard_import.json").write_text(
        json.dumps(dash, ensure_ascii=False), encoding="utf-8"
    )

    seen.update(it["uid"] for it in items)
    SEEN_FILE.write_text(json.dumps(sorted(seen)))
    print(f"{len(items)} leads mili. leads.csv aur dashboard_import.json ban gayi.")
    print(f"Inme se {sum(1 for i in items if i['phone'])} ke paas phone number hai.")


if __name__ == "__main__":
    main()