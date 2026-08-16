"""Rapatrie titres enregistrés, albums enregistrés et artistes suivis.

Tourne une fois par jour. ~130 appels pour 6 000 titres, c'est indolore.
Écrit data/library.json
"""
import sys
from common import DATA, http, write_json
from collect_listens import access_token

API = "https://api.spotify.com/v1"


def page(url, tok, key="items"):
    out, guard = [], 0
    while url and guard < 400:
        st, r = http(url, headers={"Authorization": "Bearer " + tok})
        if st != 200 or not r:
            print(f"  [avertissement] {url} -> {st}, on s'arrête là")
            break
        block = r.get(key) or r.get("artists", {}).get(key, [])
        out.extend(block)
        nxt = r.get("next") or r.get("artists", {}).get("next")
        url, guard = nxt, guard + 1
    return out


def main():
    tok = access_token()

    tracks = page(f"{API}/me/tracks?limit=50", tok)
    albums = page(f"{API}/me/albums?limit=50", tok)
    artists = page(f"{API}/me/following?type=artist&limit=50", tok)

    lib = {
        "tracks": [{"track": (i.get("track") or {}).get("name", ""),
                    "artist": ((i.get("track") or {}).get("artists") or [{}])[0].get("name", ""),
                    "album": ((i.get("track") or {}).get("album") or {}).get("name", ""),
                    "uri": (i.get("track") or {}).get("uri", ""),
                    "added": i.get("added_at", "")} for i in tracks],
        "albums": [{"album": (i.get("album") or {}).get("name", ""),
                    "artist": (((i.get("album") or {}).get("artists") or [{}])[0]).get("name", ""),
                    "uri": (i.get("album") or {}).get("uri", ""),
                    "added": i.get("added_at", "")} for i in albums],
        "artists": [{"artist": a.get("name", ""), "uri": a.get("uri", "")} for a in artists],
    }
    print(f"  {len(lib['tracks'])} titres · {len(lib['albums'])} albums · {len(lib['artists'])} artistes")
    if not any(lib.values()):
        sys.exit("[stop] bibliothèque vide — probablement un problème de scope ou de jeton")
    write_json(DATA / "library.json", lib)


if __name__ == "__main__":
    main()
