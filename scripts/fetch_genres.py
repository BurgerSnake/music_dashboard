"""Genres par artiste, depuis les genres et tags MusicBrainz.

MusicBrainz est le bon choix : gratuit, sans clé, données ouvertes et
corrigeables par la communauté. Spotify a supprimé le champ `popularity`
en février 2026 et son champ `genres` n'est plus fiable.

On réutilise les identifiants déjà en cache dans mbid_cache.json, donc
la plupart des artistes ne coûtent qu'un appel, une seule fois.

Écrit : data/genres.json
"""
import collections, datetime as dt, time, urllib.parse
from common import DATA, all_listens, http, norm, read_json, write_json

MB = "https://musicbrainz.org/ws/2"
TOP_N = 700          # artistes à classer
MAX_CALLS = 400      # plafond par passage : le reste au passage suivant

# regroupement des tags MusicBrainz en familles lisibles
FAMILIES = [
    # ORDRE IMPORTANT : du plus spécifique au plus générique.
    # "Indie / Alternative" matche "alternative rock", donc il doit passer
    # après Grunge, Britpop et compagnie, sinon il aspire tout.
    ("Shoegaze / Dream pop", ["shoegaze", "dream pop", "blackgaze", "nu gaze", "noise pop"]),
    ("Post-punk / Cold wave", ["post-punk", "postpunk", "coldwave", "cold wave", "darkwave",
                               "dark wave", "gothic rock", "no wave", "new wave"]),
    ("Britpop", ["britpop", "madchester", "baggy"]),
    ("Grunge / 90s alt", ["grunge", "alternative metal", "nu metal", "noise rock", "math rock"]),
    ("Post-rock / Drone", ["post-rock", "postrock", "drone", "slowcore", "sadcore", "ambient"]),
    ("Punk / Hardcore", ["punk rock", "hardcore", "post-hardcore", "screamo", "emo", "punk"]),
    ("Metal / Hard rock", ["doom metal", "sludge", "black metal", "death metal", "heavy metal",
                           "stoner rock", "stoner metal", "hard rock", "metal"]),
    ("Rock psyché / Garage", ["psychedelic rock", "garage rock", "krautrock", "space rock",
                              "neo-psychedelia"]),
    ("Hip-hop", ["hip hop", "hip-hop", "rap", "trap"]),
    ("Électronique", ["techno", "house", "idm", "synth-pop", "synthpop", "electropop",
                      "trip hop", "downtempo", "electronic"]),
    ("Chanson française", ["chanson", "chanson francaise", "french rock", "variete francaise"]),
    ("Folk / Americana", ["folk rock", "americana", "singer-songwriter", "country", "folk"]),
    ("Jazz / Soul / Blues", ["jazz", "soul", "funk", "rhythm and blues", "blues rock", "blues"]),
    ("Rock classique", ["classic rock", "rock and roll", "progressive rock", "southern rock",
                        "arena rock", "glam rock"]),
    ("Indie / Alternative", ["indie rock", "indie pop", "jangle pop", "twee pop", "college rock",
                             "alternative rock", "indie"]),
    ("Pop", ["art pop", "chamber pop", "bedroom pop", "pop rock", "pop"]),
]


def family(tags):
    """Première famille qui matche un tag, en respectant l'ordre de priorité."""
    low = [t.lower() for t in tags]
    for fam, keys in FAMILIES:
        for k in keys:
            if any(k == t or (len(k) > 4 and k in t) for t in low):
                return fam
    return None


def top_artists(n):
    c = collections.Counter()
    for r in all_listens():
        if r.get("ms", 0) < 30000:
            continue
        if r.get("artist"):
            c[r["artist"]] += 1
    return [a for a, _ in c.most_common(n)]


def main():
    mb = read_json(DATA / "mbid_cache.json", {})
    if mb and "mbid" not in mb:
        mb = {"mbid": mb, "checked": {}}
    ids = mb.get("mbid", {})
    G = read_json(DATA / "genres.json", {"by_artist": {}, "tags": {}, "misses": []})
    misses = set(G.get("misses", []))
    artists = top_artists(TOP_N)

    todo = [a for a in artists
            if norm(a) not in G["by_artist"] and norm(a) not in misses]
    print(f"  {len(artists)} artistes visés · {len(G['by_artist'])} déjà classés · "
          f"{len(todo)} à faire")

    calls = 0
    for a in todo:
        if calls >= MAX_CALLS:
            print(f"  plafond de {MAX_CALLS} appels atteint, suite au prochain passage")
            break
        mbid = ids.get(a.lower())
        if not mbid:                          # pas encore d'identifiant : on cherche
            q = urllib.parse.quote(f'artist:"{a}"')
            st, r = http(f"{MB}/artist?query={q}&fmt=json&limit=1")
            time.sleep(1.1); calls += 1
            if st == 200 and r and r.get("artists") and int(r["artists"][0].get("score", 0)) >= 90:
                mbid = r["artists"][0]["id"]
                ids[a.lower()] = mbid
        if not mbid:
            misses.add(norm(a))
            continue

        st, r = http(f"{MB}/artist/{mbid}?inc=genres+tags&fmt=json")
        time.sleep(1.1); calls += 1
        if st != 200 or not r:
            continue
        raw = [(g.get("name", ""), g.get("count", 0)) for g in (r.get("genres") or [])]
        raw += [(t.get("name", ""), t.get("count", 0)) for t in (r.get("tags") or [])]
        raw = [(n, c) for n, c in raw if n and c > 0]
        raw.sort(key=lambda x: -x[1])
        tags = [n for n, _ in raw][:8]
        fam = family(tags)
        if fam:
            G["by_artist"][norm(a)] = fam
            G["tags"][norm(a)] = tags[:4]
        else:
            misses.add(norm(a))

    G["misses"] = sorted(misses)
    write_json(DATA / "mbid_cache.json", {"mbid": ids, "checked": mb.get("checked", {})})
    write_json(DATA / "genres.json", G)
    counts = collections.Counter(G["by_artist"].values())
    print(f"  {len(G['by_artist'])} artistes classés, {len(misses)} sans genre exploitable")
    for fam, n in counts.most_common():
        print(f"    {fam:26s} {n}")


if __name__ == "__main__":
    main()
