"""Rapatrie la collection de vinyles et la wantlist depuis Discogs.

Discogs plafonne à 60 requêtes/minute en authentifié : on pagine par 100
et on souffle une seconde entre deux appels, largement dans les clous.

Secrets : DISCOGS_TOKEN, DISCOGS_USER
Écrit    : data/vinyl.json
"""
import time
from common import DATA, env, http, write_json

BASE = "https://api.discogs.com"


def fetch(path, tok):
    out, url, guard = [], f"{BASE}{path}?per_page=100&token={tok}", 0
    while url and guard < 60:
        st, r = http(url, headers={"Authorization": f"Discogs token={tok}"})
        if st != 200 or not r:
            print(f"  [avertissement] {path} -> {st}")
            break
        out.extend(r.get("releases", []) or r.get("wants", []))
        url = (r.get("pagination", {}).get("urls", {}) or {}).get("next")
        if url and "token=" not in url:
            url += f"&token={tok}"
        guard += 1
        time.sleep(1.1)
    return out


def flat(entry, kind):
    b = entry.get("basic_information", {}) or {}
    return {
        "kind": kind,
        "id": entry.get("id"),
        "instance_id": entry.get("instance_id"),
        "folder_id": entry.get("folder_id", 1),
        "title": b.get("title", ""),
        "artist": ", ".join(a.get("name", "").split(" (")[0] for a in b.get("artists", [])),
        "year": b.get("year") or None,
        "labels": [l.get("name", "") for l in b.get("labels", [])][:2],
        "formats": [f.get("name", "") for f in b.get("formats", [])],
        "thumb": b.get("thumb", ""),
        "added": entry.get("date_added", ""),
        "url": f"https://www.discogs.com/release/{entry.get('id')}",
    }


def main():
    tok, user = env("DISCOGS_TOKEN"), env("DISCOGS_USER")
    coll = [flat(e, "collection") for e in fetch(f"/users/{user}/collection/folders/0/releases", tok)]
    want = [flat(e, "wantlist") for e in fetch(f"/users/{user}/wants", tok)]
    print(f"  {len(coll)} disques en collection · {len(want)} en wantlist")
    write_json(DATA / "vinyl.json", {"collection": coll, "wantlist": want})


if __name__ == "__main__":
    main()
