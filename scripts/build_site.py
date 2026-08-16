"""Calcule tous les agrégats et écrit site/data/dashboard.json.

Aucun secret, aucun réseau : ne lit que data/. C'est le seul script
qui produit ce que la page affiche, donc le seul à relancer quand on
veut changer une statistique.
"""
import collections, datetime as dt, math
from common import DATA, SITE, all_listens, norm, read_json, write_json

MIN_MS = 30000        # seuil d'une écoute qui compte
try:                                       # heure locale réelle, changements d'heure inclus
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Brussels")
except Exception:
    TZ = dt.timezone(dt.timedelta(hours=1))


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ)


def main():
    raw = all_listens()
    if not raw:
        print("  aucune écoute — lance d'abord scripts/bootstrap_import.py")
        write_json(SITE / "dashboard.json", {"empty": True})
        return

    lib = read_json(DATA / "library.json", {"tracks": [], "albums": [], "artists": []})
    vinyl = read_json(DATA / "vinyl.json", {"collection": [], "wantlist": []})
    concerts = read_json(DATA / "concerts.json", [])
    releases = read_json(DATA / "releases.json", [])
    events = read_json(DATA / "events.json", [])

    liked_t = {(norm(t["artist"]), norm(t["track"])) for t in lib["tracks"]}
    saved_a = {(norm(a["artist"]), norm(a["album"])) for a in lib["albums"]}
    follow = {norm(a["artist"]) for a in lib["artists"]}
    seen_gigs = collections.Counter(norm(c.get("artist", "")) for c in concerts
                                    if c.get("date", "9") <= dt.date.today().isoformat())
    next_gig = {}
    for c in concerts:
        if c.get("date", "") > dt.date.today().isoformat():
            k = norm(c.get("artist", ""))
            next_gig[k] = min(next_gig.get(k, "9999"), c["date"])

    A = collections.defaultdict(lambda: dict(min=0.0, n=0, tracks=set(), days=set(), yr=collections.Counter()))
    B = collections.defaultdict(lambda: dict(min=0.0, n=0, tracks=set(), days=set(), artist="", uri=""))
    T = collections.defaultdict(lambda: dict(min=0.0, n=0, days=set(), artist="", uri=""))
    Y = collections.defaultdict(lambda: dict(min=0.0, n=0, art=set(), trk=set(), alb=set(), days=set()))
    hours = [0.0] * 24
    last_ts = raw[-1]["ts"]

    for r in raw:
        if r.get("ms", 0) < MIN_MS:
            continue
        d = parse(r["ts"])
        y, day, m = d.year, d.date().isoformat(), r["ms"] / 60000
        art, trk, alb = r.get("artist", ""), r.get("track", ""), r.get("album", "")
        ka, kb, kt = norm(art), (norm(art), norm(alb)), (norm(art), norm(trk))

        a = A[ka]; a["min"] += m; a["n"] += 1; a["tracks"].add(kt[1]); a["days"].add(day)
        a["yr"][y] += m; a["name"] = art
        b = B[kb]; b["min"] += m; b["n"] += 1; b["tracks"].add(kt[1]); b["days"].add(day)
        b["artist"], b["name"] = art, alb
        if r.get("album_uri"):
            b["uri"] = r["album_uri"]
        t = T[kt]; t["min"] += m; t["n"] += 1; t["days"].add(day)
        t["artist"], t["name"], t["uri"] = art, trk, r.get("uri", "")
        yy = Y[y]; yy["min"] += m; yy["n"] += 1; yy["art"].add(ka); yy["trk"].add(kt)
        yy["alb"].add(kb); yy["days"].add(day)
        hours[d.hour] += m

    years = sorted(Y)
    ov = dict(
        years=years,
        hours=[round(Y[y]["min"] / 60, 1) for y in years],
        plays=[Y[y]["n"] for y in years],
        artists=[len(Y[y]["art"]) for y in years],
        tracks=[len(Y[y]["trk"]) for y in years],
        albums=[len(Y[y]["alb"]) for y in years],
        days=[len(Y[y]["days"]) for y in years],
        eff=[], top10=[], clock=[round(h / 60, 1) for h in hours],
        updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        last_listen=last_ts,
    )
    for y in years:
        w = [a["yr"][y] for a in A.values() if a["yr"][y] > 0]
        tot = sum(w) or 1
        ent = -sum((x / tot) * math.log(x / tot) for x in w)
        ov["eff"].append(round(math.exp(ent), 1))
        ov["top10"].append(round(sum(sorted(w, reverse=True)[:10]) / tot * 100, 1))

    arts = sorted(A.items(), key=lambda kv: -kv[1]["min"])
    arts = [[v.get("name", k), round(v["min"] / 60, 1), v["n"], len(v["tracks"]), len(v["days"]),
             k in follow, seen_gigs.get(k, 0), next_gig.get(k),
             [round(v["yr"][y] / 60, 1) for y in years]]
            for k, v in arts if v["n"] >= 3]

    albs = sorted(B.items(), key=lambda kv: -kv[1]["min"])
    albs = [[v.get("name", ""), v["artist"], round(v["min"] / 60, 1), v["n"],
             len(v["tracks"]), len(v["days"]), k in saved_a, v["uri"]]
            for k, v in albs if len(v["tracks"]) >= 3]

    trks = sorted(T.items(), key=lambda kv: -kv[1]["n"])
    trks = [[v.get("name", ""), v["artist"], v["n"], round(v["min"] / 60, 1),
             len(v["days"]), k in liked_t, v["uri"]]
            for k, v in trks if v["n"] >= 4]

    hmap = {k: v for k, v in ((norm(a[0]), a[1]) for a in arts)}
    for c in concerts:
        c["hours"] = hmap.get(norm(c.get("artist", "")), 0)
    for e in events:
        e["hours"] = hmap.get(norm(e.get("artist", "")), 0)
        e["known"] = norm(e.get("artist", "")) in hmap
    for r in releases:
        r["hours"] = hmap.get(norm(r.get("artist", "")), 0)

    own = {norm(v["artist"]) + "|" + norm(v["title"]) for v in vinyl["collection"]}
    want = {norm(v["artist"]) + "|" + norm(v["title"]) for v in vinyl["wantlist"]}
    vinyl_gaps = [[a[0], a[1], a[2]] for a in albs[:120]
                  if (norm(a[1]) + "|" + norm(a[0])) not in own
                  and (norm(a[1]) + "|" + norm(a[0])) not in want][:40]

    # les 200 dernières écoutes, pour l'onglet Récent
    recent = [{"ts": r["ts"], "track": r.get("track", ""), "artist": r.get("artist", ""),
               "album": r.get("album", ""), "ms": r.get("ms", 0)}
              for r in raw[-200:]][::-1]

    out = dict(ov=ov, arts=arts, albs=albs, trks=trks, recent=recent, concerts=concerts,
               events=events, releases=releases, vinyl=vinyl, vinyl_gaps=vinyl_gaps,
               stats=dict(listens=len(raw), artists=len(arts), albums=len(albs),
                          tracks=len(trks), liked=len(lib["tracks"]),
                          saved=len(lib["albums"]), followed=len(lib["artists"]),
                          vinyls=len(vinyl["collection"]), wants=len(vinyl["wantlist"])))
    write_json(SITE / "dashboard.json", out)
    print(f"  {len(raw)} écoutes · {len(arts)} artistes · {len(albs)} albums · {len(trks)} titres")


if __name__ == "__main__":
    main()
