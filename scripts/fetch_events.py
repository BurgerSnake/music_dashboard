"""DORMANT — non branché sur aucun workflow, et l'onglet a été retiré du site.

Raison : aucune source ouverte ne couvre assez de salles pour être utile.
Bandsintown réserve ses clés aux artistes, Songkick a suspendu les nouvelles
demandes, et Ticketmaster ne voit que son propre inventaire — il ratait
Manchester Psych Fest et les salles belges indépendantes. Une liste partielle
est pire qu'aucune liste : elle laisse croire qu'on a regardé.

Le code reste ici, prêt à resservir si une source suffisante apparaît
(UiTdatabank pour la Flandre, collecteurs par salle, Skiddle pour le
Royaume-Uni). Pour le réactiver : rebrancher l'étape dans discover.yml et
restaurer l'onglet dans site/index.html.

Concerts à venir des artistes écoutés — Bandsintown + Ticketmaster.

Les deux sources sont complémentaires :
  - Bandsintown agrège les annonces des artistes eux-mêmes. Bien meilleure
    couverture des salles indépendantes (AB, Botanique, Trix…), et il renvoie
    TOUTES les dates d'un artiste dans le monde.
  - Ticketmaster ne connaît que son propre inventaire : gros festivals et
    grandes salles, mais avec des liens de billetterie fiables.

On stocke tout sans filtre géographique : le tri par pays, ville et date se
fait dans le navigateur, instantanément.

Secrets   : BANDSINTOWN_APP_ID (facultatif), TICKETMASTER_KEY (facultatif)
Réglages  : TOP_N_EVENTS, TM_GEO / TM_RADIUS_KM
Écrit     : data/events.json
"""
import collections, os, time, urllib.parse
from common import DATA, all_listens, http, norm, read_json, write_json

BIT = "https://rest.bandsintown.com/artists"
TM = "https://app.ticketmaster.com/discovery/v2/events.json"
TOP_N = int(os.environ.get("TOP_N_EVENTS", "250"))
LAT = float(os.environ.get("HOME_LAT", "50.4108"))
LON = float(os.environ.get("HOME_LON", "4.4446"))
TM_RADIUS = os.environ.get("TM_RADIUS_KM", "800")
B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat, lon, precision=5):
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
        if r.get("ms", 0) < 30000 or not r.get("artist"):
            continue
        c[r["artist"]] += 1
    return [a for a, _ in c.most_common(n)]


def row(**kw):
    kw.setdefault("tickets", "")
    return kw


def from_bandsintown(artists, app_id):
    out = []
    for i, name in enumerate(artists, 1):
        url = (f"{BIT}/{urllib.parse.quote(name, safe='')}/events?"
               + urllib.parse.urlencode({"app_id": app_id}))
        st, r = http(url)
        time.sleep(0.35)
        if st != 200 or not isinstance(r, list):
            if i <= 3 and st != 200:
                print(f"  [avertissement] Bandsintown '{name}' -> HTTP {st}")
            continue
        for e in r:
            v = e.get("venue") or {}
            offers = [o.get("url", "") for o in (e.get("offers") or [])
                      if o.get("type", "").lower() == "tickets" and o.get("url")]
            out.append(row(
                artist=name, event=e.get("title") or "",
                date=(e.get("datetime") or "")[:10],
                time=(e.get("datetime") or "")[11:16],
                venue=v.get("name", ""), city=v.get("city", ""),
                region=v.get("region", "") or "",
                country=v.get("country", ""),
                lat=v.get("latitude", ""), lon=v.get("longitude", ""),
                url=e.get("url", ""),
                tickets=offers[0] if offers else (e.get("url") or ""),
                src="bandsintown"))
        if i % 50 == 0:
            print(f"  Bandsintown {i}/{len(artists)} · {len(out)} dates")
    return out


def from_ticketmaster(artists, key):
    gp = geohash(LAT, LON)
    out = []
    for i, name in enumerate(artists, 1):
        params = urllib.parse.urlencode({
            "apikey": key, "keyword": name, "classificationName": "music",
            "geoPoint": gp, "radius": TM_RADIUS, "unit": "km",
            "size": 20, "sort": "date,asc"})
        st, r = http(f"{TM}?{params}")
        time.sleep(0.6)
        if st != 200 or not r:
            if i <= 3 and st != 200:
                print(f"  [avertissement] Ticketmaster '{name}' -> HTTP {st}")
            continue
        for e in (r.get("_embedded", {}) or {}).get("events", []):
            names = [a.get("name", "") for a in
                     (e.get("_embedded", {}) or {}).get("attractions", [])]
            if names and not any(norm(n) == norm(name) for n in names):
                continue
            ven = ((e.get("_embedded", {}) or {}).get("venues") or [{}])[0]
            loc = ven.get("location", {}) or {}
            out.append(row(
                artist=name, event=e.get("name", ""),
                date=(e.get("dates", {}).get("start", {}) or {}).get("localDate", ""),
                time=(e.get("dates", {}).get("start", {}) or {}).get("localTime", "")[:5],
                venue=ven.get("name", ""),
                city=(ven.get("city", {}) or {}).get("name", ""),
                region=((ven.get("state", {}) or {}).get("name", "")) or "",
                country=(ven.get("country", {}) or {}).get("countryCode", ""),
                lat=loc.get("latitude", ""), lon=loc.get("longitude", ""),
                url=e.get("url", ""), tickets=e.get("url", ""),
                src="ticketmaster"))
        if i % 50 == 0:
            print(f"  Ticketmaster {i}/{len(artists)} · {len(out)} dates")
    return out


def main():
    artists = top_artists(TOP_N)
    bit_id = os.environ.get("BANDSINTOWN_APP_ID", "").strip()
    tm_key = os.environ.get("TICKETMASTER_KEY", "").strip()
    print(f"  {len(artists)} artistes suivis")

    out = []
    if bit_id:
        print("  Bandsintown : toutes les dates, sans limite géographique")
        out += from_bandsintown(artists, bit_id)
    else:
        print("  Bandsintown ignoré (BANDSINTOWN_APP_ID absent)")
    if tm_key:
        print(f"  Ticketmaster : rayon {TM_RADIUS} km")
        out += from_ticketmaster(artists, tm_key)
    else:
        print("  Ticketmaster ignoré (TICKETMASTER_KEY absent)")

    # fusion : même artiste, même jour, même ville → une seule date.
    # Bandsintown gagne sur le lieu, Ticketmaster complète le lien billetterie.
    merged = {}
    for e in sorted(out, key=lambda x: (x["date"], x["src"])):
        if not e["date"]:
            continue
        k = (norm(e["artist"]), e["date"], norm(e["city"]))
        if k in merged:
            cur = merged[k]
            if not cur.get("tickets") and e.get("tickets"):
                cur["tickets"] = e["tickets"]
            cur["src"] = "les deux" if cur["src"] != e["src"] else cur["src"]
            continue
        merged[k] = e

    uniq = sorted(merged.values(), key=lambda x: x["date"])
    pays = collections.Counter(e["country"] for e in uniq if e["country"])
    print(f"  {len(out)} dates brutes → {len(uniq)} après fusion")
    print("  pays : " + " · ".join(f"{p} {n}" for p, n in pays.most_common(12)))
    print(f"  avec lien billetterie : {sum(1 for e in uniq if e['tickets'])}")
    if not uniq:
        print("  aucune date : vérifie les secrets, ou les artistes ne tournent pas.")
    write_json(DATA / "events.json", uniq)


if __name__ == "__main__":
    main()
