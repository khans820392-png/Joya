"""
Lead Finder v1
--------------
Google Places se aise business dhundta hai jinki rating achhi hai
lekin apni website nahi hai, phir top leads Telegram par bhej deta hai.

Setup:
    pip install requests
    set GOOGLE_API_KEY=...        (Google Cloud -> Places API (New) enable karo)
    set TELEGRAM_BOT_TOKEN=...    (Telegram par @BotFather se bot banao)
    set TELEGRAM_CHAT_ID=...      (apna chat id, @userinfobot se mil jata hai)

Run:
    python lead_finder.py
"""

import json
import math
import os
import urllib.parse
from pathlib import Path

import requests

# ---------------- CONFIG (yahan badlo) ----------------
CITY = "आपका शहर"          # yahan apne shehar ka naam likho
CATEGORIES = ["boutique", "designer boutique", "ladies tailor"]
MIN_RATING = 4.0
MIN_REVIEWS = 10
MAX_PAGES = 3                 # har search ke 20 results x pages
TOP_N_TO_SEND = 10            # ek baar me kitne leads bhejne hain
SEEN_FILE = Path("seen_leads.json")
# ------------------------------------------------------

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.websiteUri",
    "places.nationalPhoneNumber",
    "places.googleMapsUri",
    "nextPageToken",
])

SOCIAL_HOSTS = ("instagram.com", "facebook.com", "fb.com", "fb.me", "linktr.ee")


def search_places(query):
    """Ek query ke liye saare pages ke results laata hai."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {"textQuery": query, "pageSize": 20}
    results = []
    for _ in range(MAX_PAGES):
        r = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("places", []))
        token = data.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
    return results


def classify_website(url):
    """(has_real_website, social_link) return karta hai.
    Kai business Google par apna Instagram/Facebook page hi 'website' ke
    taur par daal dete hain; use asli website nahi maanenge."""
    if not url:
        return False, None
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(h in host for h in SOCIAL_HOSTS):
        return False, url
    return True, None


def google_search_link(name, site):
    q = f"{name} {CITY} site:{site}"
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


def score(place):
    rating = place.get("rating", 0)
    reviews = place.get("userRatingCount", 0)
    return rating * math.log(reviews + 1)


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def format_lead(p, social_link):
    name = p.get("displayName", {}).get("text", "Unknown")
    lines = [
        f"🔥 {name}",
        f"⭐ {p.get('rating')} ({p.get('userRatingCount')} reviews)",
        "🌐 Website: nahi hai",
        f"📍 {p.get('formattedAddress', '-')}",
        f"📞 {p.get('nationalPhoneNumber', 'number nahi mila')}",
        f"🗺 {p.get('googleMapsUri', '')}",
    ]
    if social_link:
        lines.append(f"📲 Social page: {social_link}")
    lines.append(f"🔎 Instagram dhundo: {google_search_link(name, 'instagram.com')}")
    lines.append(f"🔎 Facebook dhundo: {google_search_link(name, 'facebook.com')}")
    return "\n".join(lines)


def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT_ID):
        print(text, end="\n\n" + "-" * 40 + "\n\n")  # token na ho to bas print
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": TG_CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


def main():
    if not GOOGLE_API_KEY:
        raise SystemExit("GOOGLE_API_KEY set nahi hai.")

    seen = load_seen()
    leads = {}

    for cat in CATEGORIES:
        query = f"{cat} in {CITY}"
        print("Searching:", query)
        for p in search_places(query):
            pid = p["id"]
            if pid in seen or pid in leads:
                continue
            if p.get("rating", 0) < MIN_RATING:
                continue
            if p.get("userRatingCount", 0) < MIN_REVIEWS:
                continue
            has_site, social = classify_website(p.get("websiteUri"))
            if has_site:
                continue
            leads[pid] = (p, social)

    ranked = sorted(leads.values(), key=lambda x: score(x[0]), reverse=True)
    top = ranked[:TOP_N_TO_SEND]

    if not top:
        print("Koi nayi lead nahi mili.")
        return

    send_telegram(f"📋 {len(top)} nayi leads mili ({CITY})")
    for p, social in top:
        send_telegram(format_lead(p, social))
        seen.add(p["id"])

    save_seen(seen)
    print(f"{len(top)} leads bheji gayi.")


if __name__ == "__main__":
    main()