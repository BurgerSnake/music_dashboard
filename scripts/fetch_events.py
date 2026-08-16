"""Concerts à venir des artistes écoutés, dans un rayon autour de chez toi.

Ticketmaster Discovery : clé gratuite, 2 requêtes/seconde, 5 000 par jour.
On interroge les N artistes les plus écoutés, une requête chacun.

Secret   : TICKETMASTER_KEY
Réglages : HOME_LAT / HOME_LON / RADIUS_KM (variables du workflow)
Écrit    : data/events.json
"""
import collections, os, time, urllib.parse
from common import DATA, all_listens, env, http, write_json

TM = "https://app.ticketmaster.com/discovery/v2/events.json"
TOP_N = 100
LAT = os.environ.get("HOME_LAT", "50.4108")   # Charleroi
LON = os.environ.get("HOME_LON", "4.4446")
RADIUS = os.environ.get("RADIUS_KM", "350")


def top_artists(n):
    c = collections.Counter()
    for r in all_listens():
        if r.get("artist"):
            c[r["artist"]] += 1
    return [a for a, _ in c.most_common(n)]


def main():
    key = env("TICKETMASTER_KEY")
    out = []
    artists = top_artists(TOP_N)
    print(f"  {len(artists)} artistes · rayon {RADIUS} km autour de {LAT},{LON}")

    for i, name in enumerate(artists, 1):
        params = urllib.parse.urlencode({
            "apikey": key, "keyword": name, "classificationName": "music",
            "latlong": f"{LAT},{LON}", "radius": RADIUS, "unit": "km",
            "size": 20, "sort": "date,asc"})
        st, r = http(f"{TM}?{params}")
        time.sleep(0.6)                      # on reste sous 2 req/s
        if st != 200 or not r:
            continue
        for e in (r.get("_embedded", {}) or {}).get("events", []):
            names = [a.get("name", "") for a in
                     (e.get("_embedded", {}) or {}).get("attractions", [])]
            if not any(n.lower() == name.lower() for n in names):
                continue                     # le mot-clé matche large, on recadre
            ven = ((e.get("_embedded", {}) or {}).get("venues") or [{}])[0]
            out.append({
                "artist": name,
                "event": e.get("name", ""),
                "date": (e.get("dates", {}).get("start", {}) or {}).get("localDate", ""),
                "time": (e.get("dates", {}).get("start", {}) or {}).get("localTime", ""),
                "venue": ven.get("name", ""),
                "city": (ven.get("city", {}) or {}).get("name", ""),
                "country": (ven.get("country", {}) or {}).get("countryCode", ""),
                "url": e.get("url", ""),
                "status": (e.get("dates", {}).get("status", {}) or {}).get("code", ""),
            })
        if i % 25 == 0:
            print(f"  {i}/{len(artists)}…")

    seen, uniq = set(), []
    for e in sorted(out, key=lambda x: x["date"]):
        k = (e["artist"], e["date"], e["venue"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    print(f"  {len(uniq)} dates trouvées")
    write_json(DATA / "events.json", uniq)


if __name__ == "__main__":
    main()
