"""Sorties d'albums des artistes les plus écoutés, via MusicBrainz.

MusicBrainz est gratuit et sans clé, mais impose 1 requête/seconde et un
User-Agent identifiable. On limite donc aux N artistes les plus écoutés et
on met en cache les identifiants MBID pour ne pas les rechercher chaque nuit.

Écrit : data/releases.json, data/mbid_cache.json
"""
import collections, datetime as dt, time, urllib.parse
from common import DATA, all_listens, http, read_json, write_json

MB = "https://musicbrainz.org/ws/2"
TOP_N = 120          # artistes suivis pour les sorties
STALE_DAYS = 10      # on ne réinterroge un artiste que tous les 10 jours
MAX_CALLS = 70       # plafond d'appels par passage, pour borner la durée
WINDOW_BACK = 400    # jours d'historique de sorties à conserver
WINDOW_FWD = 400     # jours d'annonces à venir


def top_artists(n):
    c = collections.Counter()
    for r in all_listens():
        if r.get("artist"):
            c[r["artist"]] += 1
    return [a for a, _ in c.most_common(n)]


def find_mbid(name, cache):
    key = name.lower()
    if key in cache:
        return cache[key]
    q = urllib.parse.quote(f'artist:"{name}"')
    st, r = http(f"{MB}/artist?query={q}&fmt=json&limit=1")
    time.sleep(1.1)
    mbid = None
    if st == 200 and r and r.get("artists"):
        top = r["artists"][0]
        if int(top.get("score", 0)) >= 90:
            mbid = top["id"]
    cache[key] = mbid
    return mbid


def releases_for(mbid):
    st, r = http(f"{MB}/release-group?artist={mbid}&type=album|ep&fmt=json&limit=100")
    time.sleep(1.1)
    if st != 200 or not r:
        return []
    return r.get("release-groups", [])


def main():
    raw = read_json(DATA / "mbid_cache.json", {})
    # migration depuis l'ancien format plat {nom: mbid}
    if raw and "mbid" not in raw:
        raw = {"mbid": raw, "checked": {}}
    cache, checked = raw.get("mbid", {}), raw.get("checked", {})
    keep = read_json(DATA / "releases.json", [])
    today = dt.date.today()
    lo = (today - dt.timedelta(days=WINDOW_BACK)).isoformat()
    hi = (today + dt.timedelta(days=WINDOW_FWD)).isoformat()

    artists = top_artists(TOP_N)
    limit = (today - dt.timedelta(days=STALE_DAYS)).isoformat()
    due = [a for a in artists if checked.get(a.lower(), "") < limit]
    due.sort(key=lambda a: checked.get(a.lower(), ""))     # les plus anciens d'abord
    calls = 0
    budget = [a for a in due if (calls := calls + (1 if a.lower() in cache else 2)) <= MAX_CALLS]
    fresh = {a for a in artists if a not in budget}
    print(f"  {len(artists)} artistes suivis · {len(due)} à rafraîchir · "
          f"{len(budget)} traités ce passage (plafond {MAX_CALLS} appels)")

    # on repart des sorties déjà connues pour les artistes non réinterrogés
    out = [r for r in keep if r.get("artist") in fresh]

    for i, name in enumerate(budget, 1):
        mbid = find_mbid(name, cache)
        checked[name.lower()] = today.isoformat()
        if not mbid:
            continue
        for rg in releases_for(mbid):
            d = rg.get("first-release-date", "")
            if len(d) == 4:
                d += "-01-01"
            elif len(d) == 7:
                d += "-01"
            if not d or not (lo <= d <= hi):
                continue
            out.append({"date": d, "artist": name, "title": rg.get("title", ""),
                        "type": rg.get("primary-type", ""),
                        "mbid": rg.get("id", ""),
                        "url": f"https://musicbrainz.org/release-group/{rg.get('id','')}"})
        if i % 20 == 0:
            print(f"  {i}/{len(budget)}…")
            write_json(DATA / "mbid_cache.json", {"mbid": cache, "checked": checked})

    seen, uniq = set(), []
    for r in sorted(out, key=lambda x: x["date"], reverse=True):
        k = (r["artist"], r["title"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    print(f"  {len(uniq)} sorties retenues entre {lo} et {hi} "
          f"(dont {len(out) - sum(1 for r in out if r.get('artist') in fresh)} nouvelles)")
    write_json(DATA / "mbid_cache.json", {"mbid": cache, "checked": checked})
    write_json(DATA / "releases.json", uniq)


if __name__ == "__main__":
    main()
