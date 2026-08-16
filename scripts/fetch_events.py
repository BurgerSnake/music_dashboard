"""Concerts à venir des artistes écoutés, dans un rayon autour de chez toi.

Ticketmaster Discovery : clé gratuite, 2 requêtes/seconde, 5 000 par jour.
On interroge les N artistes les plus écoutés, une requête chacun.

Secret   : TICKETMASTER_KEY
Réglages : HOME_LAT / HOME_LON / RADIUS_KM (variables du workflow)
Écrit    : data/events.json
"""
import collections, os, time, urllib.parse
from common import DATA, all_listens, env, http, norm, write_json

TM = "https://app.ticketmaster.com/discovery/v2/events.json"
TOP_N = 100
LAT = float(os.environ.get("HOME_LAT", "50.4108"))   # Charleroi
LON = float(os.environ.get("HOME_LON", "4.4446"))
RADIUS = os.environ.get("RADIUS_KM", "350")

B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat, lon, precision=5):
    """Ticketmaster a deprecie latlong au profit de geoPoint, qui attend un geohash."""
    la, lo = [-90.0, 90.0], [-180.0, 180.0]
    bits, bit, ch, out, even = [16, 8, 4, 2, 1], 0, 0, [], True
    while len(out) < precision:
        if even:
            mid = (lo[0] + lo[1]) / 2
            if lon > mid:
                ch |= bits[bit]; lo[0] = mid
            else:
                lo[1] = mid
        else:
            mid = (la[0] + la[1]) / 2
            if lat > mid:
                ch |= bits[bit]; la[0] = mid
            else:
                la[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            out.append(B32[ch]); bit = 0; ch = 0
    return "".join(out)


def top_artists(n):
    c = collections.Counter()
    for r in all_listens():
        if r.get("artist"):
            c[r["artist"]] += 1
    return [a for a, _ in c.most_common(n)]


def main():
    key = env("TICKETMASTER_KEY")
    gp = geohash(LAT, LON)
    out, hits = [], 0
    artists = top_artists(TOP_N)
    print(f"  {len(artists)} artistes · rayon {RADIUS} km autour de {LAT},{LON} (geoPoint={gp})")

    for i, name in enumerate(artists, 1):
        params = urllib.parse.urlencode({
            "apikey": key, "keyword": name, "classificationName": "music",
            "geoPoint": gp, "radius": RADIUS, "unit": "km",
            "size": 20, "sort": "date,asc"})
        st, r = http(f"{TM}?{params}")
        time.sleep(0.6)                      # on reste sous 2 req/s
        if st != 200:
            if i <= 3:
                print(f"  [avertissement] '{name}' -> HTTP {st} ; verifie TICKETMASTER_KEY")
            continue
        if not r:
            continue
        for e in (r.get("_embedded", {}) or {}).get("events", []):
            names = [a.get("name", "") for a in
                     (e.get("_embedded", {}) or {}).get("attractions", [])]
            # rapprochement souple : accents, casse et "The" ignores
            if names and not any(norm(n) == norm(name) for n in names):
                continue
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
            hits += 1
        if i % 25 == 0:
            print(f"  {i}/{len(artists)} · {hits} dates jusqu'ici")

    seen, uniq = set(), []
    for e in sorted(out, key=lambda x: x["date"]):
        k = (e["artist"], e["date"], e["venue"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    print(f"  {len(uniq)} dates retenues")
    if not uniq:
        print("  aucune date : soit la cle est invalide, soit le rayon est trop petit,")
        print("  soit Ticketmaster ne couvre pas ces salles (frequent pour les petites")
        print("  salles belges, qui vendent via leur propre billetterie).")
    write_json(DATA / "events.json", uniq)


if __name__ == "__main__":
    main()
