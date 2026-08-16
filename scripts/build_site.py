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

PERIODS = [("j1", "24 heures", 1), ("j7", "7 jours", 7), ("j30", "30 jours", 30),
           ("j180", "6 mois", 180), ("j365", "1 an", 365), ("all", "Depuis le début", None)]


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ)


def top(counter, n, key=lambda v: v["min"]):
    return sorted(counter.items(), key=lambda kv: -key(kv[1]))[:n]


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
    images = read_json(DATA / "images.json", {"artists": {}, "albums": {}})
    today = dt.date.today().isoformat()

    liked_t = {(norm(t["artist"]), norm(t["track"])) for t in lib["tracks"]}
    saved_a = {(norm(a["artist"]), norm(a["album"])) for a in lib["albums"]}
    follow = {norm(a["artist"]) for a in lib["artists"]}
    seen_gigs = collections.Counter(norm(c.get("artist", "")) for c in concerts
                                    if c.get("date", "9") <= today)
    next_gig = {}
    for c in concerts:
        if c.get("date", "") > today:
            k = norm(c.get("artist", ""))
            next_gig[k] = min(next_gig.get(k, "9999"), c["date"])

    now = dt.datetime.now(dt.timezone.utc)
    cutoffs = {pid: (now - dt.timedelta(days=d)).isoformat() if d else ""
               for pid, _, d in PERIODS}

    def blank():
        return dict(min=0.0, n=0, tracks=set(), days=set(), yr=collections.Counter(),
                    artist="", uri="", name="")

    A = collections.defaultdict(blank)
    B = collections.defaultdict(blank)
    T = collections.defaultdict(blank)
    Y = collections.defaultdict(lambda: dict(min=0.0, n=0, art=set(), trk=set(), alb=set(), days=set()))
    P = {pid: dict(A=collections.defaultdict(blank), B=collections.defaultdict(blank),
                   T=collections.defaultdict(blank), min=0.0, n=0, days=set(),
                   clock=[0.0] * 24, dow=[0.0] * 7) for pid, _, _ in PERIODS}
    clock = [0.0] * 24

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
        clock[d.hour] += m

        for pid, _, _ in PERIODS:                       # fenêtres glissantes
            if cutoffs[pid] and r["ts"] < cutoffs[pid]:
                continue
            p = P[pid]
            p["min"] += m; p["n"] += 1; p["days"].add(day)
            p["clock"][d.hour] += m; p["dow"][d.weekday()] += m
            pa = p["A"][ka]; pa["min"] += m; pa["n"] += 1; pa["name"] = art; pa["tracks"].add(kt[1])
            pb = p["B"][kb]; pb["min"] += m; pb["n"] += 1; pb["name"] = alb; pb["artist"] = art
            pt = p["T"][kt]; pt["min"] += m; pt["n"] += 1; pt["name"] = trk; pt["artist"] = art

    years = sorted(Y)
    ov = dict(
        years=years,
        hours=[round(Y[y]["min"] / 60, 1) for y in years],
        plays=[Y[y]["n"] for y in years],
        artists=[len(Y[y]["art"]) for y in years],
        tracks=[len(Y[y]["trk"]) for y in years],
        albums=[len(Y[y]["alb"]) for y in years],
        days=[len(Y[y]["days"]) for y in years],
        eff=[], top10=[], clock=[round(h / 60, 1) for h in clock],
        updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        last_listen=raw[-1]["ts"],
    )
    for y in years:
        w = [a["yr"][y] for a in A.values() if a["yr"][y] > 0]
        tot = sum(w) or 1
        ent = -sum((x / tot) * math.log(x / tot) for x in w)
        ov["eff"].append(round(math.exp(ent), 1))
        ov["top10"].append(round(sum(sorted(w, reverse=True)[:10]) / tot * 100, 1))

    per = {}
    for pid, label, days in PERIODS:
        p = P[pid]
        tot = p["min"] or 1
        w = sorted((v["min"] for v in p["A"].values()), reverse=True)
        ent = -sum((x / tot) * math.log(x / tot) for x in w if x > 0)
        per[pid] = dict(
            label=label, days=days,
            hours=round(p["min"] / 60, 1), plays=p["n"], actifs=len(p["days"]),
            artists=len(p["A"]), albums=len(p["B"]), tracks=len(p["T"]),
            eff=round(math.exp(ent), 1) if w else 0,
            top10=round(sum(w[:10]) / tot * 100, 1) if w else 0,
            clock=[round(x / 60, 1) for x in p["clock"]],
            dow=[round(x / 60, 1) for x in p["dow"]],
            topA=[[v["name"], round(v["min"] / 60, 1), v["n"], len(v["tracks"])]
                  for _, v in top(p["A"], 40)],
            topB=[[v["name"], v["artist"], round(v["min"] / 60, 1), v["n"]]
                  for _, v in top(p["B"], 30)],
            topT=[[v["name"], v["artist"], v["n"], round(v["min"] / 60, 1)]
                  for _, v in top(p["T"], 30, key=lambda v: v["n"])],
        )

    arts = [[v["name"], round(v["min"] / 60, 1), v["n"], len(v["tracks"]), len(v["days"]),
             k in follow, seen_gigs.get(k, 0), next_gig.get(k),
             [round(v["yr"][y] / 60, 1) for y in years]]
            for k, v in top(A, 10 ** 6) if v["n"] >= 3]
    albs = [[v["name"], v["artist"], round(v["min"] / 60, 1), v["n"],
             len(v["tracks"]), len(v["days"]), k in saved_a, v["uri"]]
            for k, v in top(B, 10 ** 6) if len(v["tracks"]) >= 3]
    trks = [[v["name"], v["artist"], v["n"], round(v["min"] / 60, 1),
             len(v["days"]), k in liked_t, v["uri"]]
            for k, v in top(T, 10 ** 6, key=lambda v: v["n"]) if v["n"] >= 4]

    hmap = {norm(a[0]): a[1] for a in arts}
    nmap = {norm(a[0]): a[0] for a in arts}
    pt = {k: v["n"] for k, v in T.items()}
    pb = {k: v["n"] for k, v in B.items()}
    pa = {k: v["n"] for k, v in A.items()}

    library = dict(
        tracks=[[t["track"], t["artist"], t["album"], pt.get((norm(t["artist"]), norm(t["track"])), 0),
                 t.get("uri", "")] for t in lib["tracks"]],
        albums=[[a["album"], a["artist"], pb.get((norm(a["artist"]), norm(a["album"])), 0),
                 a.get("uri", "")] for a in lib["albums"]],
        artists=[[a["artist"], pa.get(norm(a["artist"]), 0),
                  round(A.get(norm(a["artist"]), {"min": 0})["min"] / 60, 1)] for a in lib["artists"]],
    )

    for c in concerts:
        c["hours"] = hmap.get(norm(c.get("artist", "")), 0)
    for e in events:
        e["hours"] = hmap.get(norm(e.get("artist", "")), 0)
    for r in releases:
        r["hours"] = hmap.get(norm(r.get("artist", "")), 0)

    own = {norm(v["artist"]) + "|" + norm(v["title"]) for v in vinyl["collection"]}
    want = {norm(v["artist"]) + "|" + norm(v["title"]) for v in vinyl["wantlist"]}
    vinyl_gaps = [[a[0], a[1], a[2]] for a in albs[:150]
                  if (norm(a[1]) + "|" + norm(a[0])) not in own
                  and (norm(a[1]) + "|" + norm(a[0])) not in want][:50]

    recent = [{"ts": r["ts"], "track": r.get("track", ""), "artist": r.get("artist", ""),
               "album": r.get("album", ""), "ms": r.get("ms", 0)}
              for r in raw[-200:]][::-1]

    out = dict(ov=ov, per=per, arts=arts, albs=albs, trks=trks, recent=recent,
               library=library, concerts=concerts, events=events, releases=releases,
               vinyl=vinyl, vinyl_gaps=vinyl_gaps, images=images,
               names=sorted(nmap.values(), key=lambda s: s.lower()),
               stats=dict(listens=len(raw), artists=len(arts), albums=len(albs),
                          tracks=len(trks), liked=len(lib["tracks"]),
                          saved=len(lib["albums"]), followed=len(lib["artists"]),
                          vinyls=len(vinyl["collection"]), wants=len(vinyl["wantlist"])))
    write_json(SITE / "dashboard.json", out, compact=True)
    print(f"  {len(raw)} écoutes · {len(arts)} artistes · {len(albs)} albums · {len(trks)} titres")
    print(f"  périodes : " + " · ".join(f"{p['label']} {p['hours']}h" for p in per.values()))
    print(f"  images : {len(images.get('artists', {}))} artistes, {len(images.get('albums', {}))} pochettes")


if __name__ == "__main__":
    main()
