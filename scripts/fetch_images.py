"""Images d'artistes et pochettes d'albums, via l'API publique Deezer.

Deezer est le meilleur choix ici : aucune clé, aucune expiration, aucun
abonnement requis. Contrairement à Spotify, ça continuera de marcher le jour
où tu changes de plateforme.

Tout est mis en cache dans data/images.json : les passages suivants ne
redemandent que les nouveautés.

Écrit : data/images.json
"""
import collections, time, urllib.parse
from common import DATA, all_listens, http, norm, read_json, write_json

DZ = "https://api.deezer.com"
TOP_ARTISTS = 600
TOP_ALBUMS = 500
PAUSE = 0.22          # Deezer tolère ~50 requêtes / 5 s, on reste large


def ranked():
    a, b = collections.Counter(), collections.Counter()
    for r in all_listens():
        if r.get("ms", 0) < 30000:
            continue
        art = r.get("artist", "")
        if not art:
            continue
        a[art] += 1
        if r.get("album"):
            b[(art, r["album"])] += 1
    return [x for x, _ in a.most_common(TOP_ARTISTS)], [x for x, _ in b.most_common(TOP_ALBUMS)]


def search(kind, query):
    url = f"{DZ}/search/{kind}?" + urllib.parse.urlencode({"q": query, "limit": 1})
    st, r = http(url)
    time.sleep(PAUSE)
    if st != 200 or not r or not r.get("data"):
        return None
    d = r["data"][0]
    return d.get("picture_medium") or d.get("cover_medium") or None


def main():
    img = read_json(DATA / "images.json", {"artists": {}, "albums": {}, "misses": []})
    misses = set(img.get("misses", []))
    arts, albs = ranked()

    todo_a = [a for a in arts if norm(a) not in img["artists"] and "a:" + norm(a) not in misses]
    todo_b = [(a, b) for a, b in albs
              if f"{norm(a)}|{norm(b)}" not in img["albums"]
              and "b:" + f"{norm(a)}|{norm(b)}" not in misses]
    print(f"  {len(todo_a)} artistes et {len(todo_b)} albums à chercher "
          f"(déjà en cache : {len(img['artists'])} / {len(img['albums'])})")

    for i, a in enumerate(todo_a, 1):
        u = search("artist", a)
        if u:
            img["artists"][norm(a)] = u
        else:
            misses.add("a:" + norm(a))
        if i % 50 == 0:
            print(f"  artistes {i}/{len(todo_a)}")
            img["misses"] = sorted(misses)
            write_json(DATA / "images.json", img)

    for i, (a, b) in enumerate(todo_b, 1):
        u = search("album", f'artist:"{a}" album:"{b}"') or search("album", f"{a} {b}")
        k = f"{norm(a)}|{norm(b)}"
        if u:
            img["albums"][k] = u
        else:
            misses.add("b:" + k)
        if i % 50 == 0:
            print(f"  albums {i}/{len(todo_b)}")
            img["misses"] = sorted(misses)
            write_json(DATA / "images.json", img)

    img["misses"] = sorted(misses)
    print(f"  total : {len(img['artists'])} artistes, {len(img['albums'])} pochettes, "
          f"{len(misses)} introuvables")
    write_json(DATA / "images.json", img)


if __name__ == "__main__":
    main()
