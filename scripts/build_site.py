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
    images = read_json(DATA / "images.json", {"artists": {}, "albums": {}})
    gen = read_json(DATA / "genres.json", {"by_artist": {}, "tags": {}})
    GEN = gen.get("by_artist", {})
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

    # Fenêtres en JOURS CALENDAIRES locaux, et non en heures glissantes :
    # c'est plus intuitif, et surtout ça donne exactement les mêmes chiffres
    # que la période personnalisée calculée depuis la matrice.
    td = dt.datetime.now(TZ).date()
    cutoffs = {pid: (td - dt.timedelta(days=d - 1)).isoformat() if d else ""
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

        for pid, _, _ in PERIODS:                       # fenêtres en jours entiers
            if cutoffs[pid] and day < cutoffs[pid]:
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

    # granularité de la courbe selon la fenêtre
    GRAIN = {"j1": "hour", "j7": "day", "j30": "day", "j180": "month",
             "j365": "month", "all": "year"}

    def series(pid, grain):
        buck = collections.Counter()
        cut = cutoffs[pid]
        for r in raw:
            if r.get("ms", 0) < MIN_MS:
                continue
            d = parse(r["ts"])
            day = d.date().isoformat()
            if cut and day < cut:
                continue
            k = {"hour": f"{d.hour:02d}h", "day": day,
                 "month": day[:7], "year": day[:4]}[grain]
            buck[k] += r["ms"] / 60000
        if grain == "hour":
            keys = [f"{h:02d}h" for h in range(24)]
        else:
            keys = sorted(buck)
            if grain == "day" and cut:      # on montre aussi les jours à zéro
                a = dt.date.fromisoformat(cut)
                keys = [(a + dt.timedelta(days=i)).isoformat()
                        for i in range((td - a).days + 1)]
        short = {"hour": lambda k: k, "day": lambda k: k[8:10] + "/" + k[5:7],
                 "month": lambda k: k[5:7] + "/" + k[2:4], "year": lambda k: k}[grain]
        return dict(grain=grain, labels=[short(k) for k in keys],
                    values=[round(buck.get(k, 0) / 60, 2) for k in keys])

    def genre_share(adict):
        """Part des heures par famille de genre, sur les artistes classés."""
        g = collections.Counter()
        for k, v in adict.items():
            fam = GEN.get(k)
            if fam:
                g[fam] += v["min"]
        tot = sum(g.values())
        if not tot:
            return dict(couverture=0, parts=[])
        classed = sum(v["min"] for k, v in adict.items() if GEN.get(k))
        whole = sum(v["min"] for v in adict.values()) or 1
        return dict(couverture=round(classed / whole * 100, 1),
                    parts=[[fam, round(m / tot * 100, 1), round(m / 60, 1)]
                           for fam, m in g.most_common()])

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
            serie=series(pid, GRAIN[pid]),
            genres=genre_share(p["A"]),
            clock=[round(x / 60, 1) for x in p["clock"]],
            dow=[round(x / 60, 1) for x in p["dow"]],
            # mêmes champs que les listes globales, pour que les filtres
            # (non suivi / pas liké / concert) fonctionnent sur toutes les périodes
            topA=[[v["name"], round(v["min"] / 60, 1), v["n"], len(v["tracks"]), 0,
                   k in follow, seen_gigs.get(k, 0), next_gig.get(k), None, GEN.get(k, "")]
                  for k, v in top(p["A"], 300)],
            topB=[[v["name"], v["artist"], round(v["min"] / 60, 1), v["n"], 0, 0,
                   k in saved_a, ""]
                  for k, v in top(p["B"], 250)],
            topT=[[v["name"], v["artist"], v["n"], round(v["min"] / 60, 1), 0,
                   k in liked_t, ""]
                  for k, v in top(p["T"], 250, key=lambda v: v["n"])],
        )

    gy = collections.defaultdict(lambda: collections.Counter())
    for k, v in A.items():
        fam = GEN.get(k)
        if not fam:
            continue
        for y, m in v["yr"].items():
            gy[y][fam] += m
    fams = sorted({f for c in gy.values() for f in c},
                  key=lambda f: -sum(c.get(f, 0) for c in gy.values()))
    ov["genre_fams"] = fams
    ov["genre_years"] = {f: [round(gy[y][f] / (sum(gy[y].values()) or 1) * 100, 1)
                             for y in years] for f in fams}

    arts = [[v["name"], round(v["min"] / 60, 1), v["n"], len(v["tracks"]), len(v["days"]),
             k in follow, seen_gigs.get(k, 0), next_gig.get(k),
             [round(v["yr"][y] / 60, 1) for y in years], GEN.get(k, "")]
            for k, v in top(A, 10 ** 6) if v["n"] >= 3]
    albs = [[v["name"], v["artist"], round(v["min"] / 60, 1), v["n"],
             len(v["tracks"]), len(v["days"]), k in saved_a, v["uri"]]
            for k, v in top(B, 10 ** 6) if len(v["tracks"]) >= 3]
    trks = [[v["name"], v["artist"], v["n"], round(v["min"] / 60, 1),
             len(v["days"]), k in liked_t, v["uri"]]
            for k, v in top(T, 10 ** 6, key=lambda v: v["n"]) if v["n"] >= 4]

    # Un titre liké mais jamais joué n'apparaissait nulle part : on l'ajoute
    # aux listes principales avec des compteurs à zéro, pour supprimer
    # l'onglet Bibliothèque et tout regrouper au même endroit.
    have_a = {norm(a[0]) for a in arts}
    for a in lib["artists"]:
        if norm(a["artist"]) not in have_a:
            have_a.add(norm(a["artist"]))
            arts.append([a["artist"], 0, 0, 0, 0, True, seen_gigs.get(norm(a["artist"]), 0),
                         next_gig.get(norm(a["artist"])), [0] * len(years),
                         GEN.get(norm(a["artist"]), "")])
    have_b = {(norm(a[1]), norm(a[0])) for a in albs}
    for a in lib["albums"]:
        k = (norm(a["artist"]), norm(a["album"]))
        if k not in have_b:
            have_b.add(k)
            albs.append([a["album"], a["artist"], 0, 0, 0, 0, True, a.get("uri", "")])
    have_t = {(norm(t[1]), norm(t[0])) for t in trks}
    for t in lib["tracks"]:
        k = (norm(t["artist"]), norm(t["track"]))
        if k not in have_t:
            have_t.add(k)
            trks.append([t["track"], t["artist"], 0, 0, 0, True, t.get("uri", "")])
    print(f"  listes complétées par la bibliothèque : {len(arts)} artistes, "
          f"{len(albs)} albums, {len(trks)} titres")

    hmap = {norm(a[0]): a[1] for a in arts}
    nmap = {norm(a[0]): a[0] for a in arts}
    pt = {k: v["n"] for k, v in T.items()}
    pb = {k: v["n"] for k, v in B.items()}
    pa = {k: v["n"] for k, v in A.items()}

    # Spotify garde une entrée par version d'un titre (album, remaster, live,
    # compilation) : on fusionne sur artiste + titre normalisés, sinon la
    # bibliothèque affiche trois fois "Here Comes Your Man".
    def dedup(rows, keyf):
        seen, out = {}, []
        for r in rows:
            k = keyf(r)
            if k in seen:
                seen[k][-1] += 1          # compteur de versions
                continue
            seen[k] = r + [1]
            out.append(seen[k])
        return out

    library = dict(
        tracks=dedup([[t["track"], t["artist"], t["album"],
                       pt.get((norm(t["artist"]), norm(t["track"])), 0), t.get("uri", "")]
                      for t in lib["tracks"]], lambda r: (norm(r[1]), norm(r[0]))),
        albums=dedup([[a["album"], a["artist"],
                       pb.get((norm(a["artist"]), norm(a["album"])), 0), a.get("uri", "")]
                      for a in lib["albums"]], lambda r: (norm(r[1]), norm(r[0]))),
        artists=dedup([[a["artist"], pa.get(norm(a["artist"]), 0),
                        round(A.get(norm(a["artist"]), {"min": 0})["min"] / 60, 1)]
                       for a in lib["artists"]], lambda r: norm(r[0])),
    )
    print(f"  bibliothèque dédoublonnée : {len(lib['tracks'])} → {len(library['tracks'])} titres, "
          f"{len(lib['albums'])} → {len(library['albums'])} albums")


    for c in concerts:
        c["hours"] = hmap.get(norm(c.get("artist", "")), 0)
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

    # ---- matrice creuse jour × artiste et jour × album ----
    # Fichier séparé, chargé seulement quand on ouvre une période personnalisée :
    # le tableau de bord principal reste léger. Tableaux d'entiers parallèles
    # plutôt que des triplets : ça se compresse beaucoup mieux.
    d0 = dt.date.fromisoformat(min(parse(r["ts"]).date().isoformat() for r in raw[:200]))
    cellA, cellB = collections.Counter(), collections.Counter()
    cntA, cntB = collections.Counter(), collections.Counter()
    iA, iB, labA, labB = {}, {}, [], []
    for r in raw:
        if r.get("ms", 0) < MIN_MS:
            continue
        d = parse(r["ts"]).date()
        off = (d - d0).days
        if off < 0:
            continue
        art, alb = r.get("artist", ""), r.get("album", "")
        ka = norm(art)
        if ka not in iA:
            iA[ka] = len(labA); labA.append(art)
        cellA[(off, iA[ka])] += r["ms"] / 60000
        cntA[(off, iA[ka])] += 1
        if alb:
            kb = norm(art) + "|" + norm(alb)
            if kb not in iB:
                iB[kb] = len(labB)
                shown = B.get((norm(art), norm(alb)), {}).get("name") or alb
                labB.append([shown, art])
            cellB[(off, iB[kb])] += r["ms"] / 60000
            cntB[(off, iB[kb])] += 1

    def pack(cells, counts):
        ks = sorted(cells)
        return dict(day=[k[0] for k in ks], idx=[k[1] for k in ks],
                    cmin=[int(round(cells[k] * 100)) for k in ks],  # centièmes de minute
                    n=[counts[k] for k in ks])

    matrix = dict(d0=d0.isoformat(), artists=labA, albums=labB,
                  A=pack(cellA, cntA), B=pack(cellB, cntB))
    write_json(SITE / "matrix.json", matrix, compact=True)

    # Les titres vivent dans leur propre fichier : bien plus volumineux, et
    # utile seulement quand on ouvre l'onglet Titres sur une période libre.
    cellT, cntT, iT, labT = collections.Counter(), collections.Counter(), {}, []
    for r in raw:
        if r.get("ms", 0) < MIN_MS:
            continue
        d = parse(r["ts"]).date()
        off = (d - d0).days
        if off < 0 or not r.get("track"):
            continue
        art, trk = r.get("artist", ""), r["track"]
        k = norm(art) + "|" + norm(trk)
        if k not in iT:
            iT[k] = len(labT); labT.append([trk, art])
        cellT[(off, iT[k])] += r["ms"] / 60000
        cntT[(off, iT[k])] += 1
    write_json(SITE / "matrix_tracks.json",
               dict(d0=d0.isoformat(), tracks=labT, T=pack(cellT, cntT)), compact=True)
    print(f"  matrice : {len(cellA)} cellules artiste, {len(cellB)} album, {len(cellT)} titre")

    out = dict(ov=ov, per=per, matrix_ready=True, arts=arts, albs=albs, trks=trks, recent=recent,
               library=library, concerts=concerts, releases=releases,
               vinyl=vinyl, vinyl_gaps=vinyl_gaps, images=images,
               names=sorted(nmap.values(), key=lambda s: s.lower()),
               stats=dict(listens=len(raw), artists=len(arts), albums=len(albs),
                          tracks=len(trks), liked=len(lib["tracks"]),
                          saved=len(lib["albums"]), followed=len(lib["artists"]),
                          vinyls=len(vinyl["collection"]), wants=len(vinyl["wantlist"]),
                          genres=len(GEN)))
    write_json(SITE / "dashboard.json", out, compact=True)
    print(f"  {len(raw)} écoutes · {len(arts)} artistes · {len(albs)} albums · {len(trks)} titres")
    print(f"  périodes : " + " · ".join(f"{p['label']} {p['hours']}h" for p in per.values()))
    print(f"  images : {len(images.get('artists', {}))} artistes, {len(images.get('albums', {}))} pochettes")


if __name__ == "__main__":
    main()
