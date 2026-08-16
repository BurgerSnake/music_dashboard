"""Exécute les actions déposées par le site, puis vide la file.

Le site ne peut pas contenir de secret : il écrit une intention dans
data/actions.jsonl, ce script l'exécute côté Actions où les secrets vivent.

Types gérés :
  {"type":"discogs_want_add",    "release_id":123456}
  {"type":"discogs_want_remove", "release_id":123456}
  {"type":"discogs_coll_add",    "release_id":123456}
  {"type":"spotify_save",        "uris":["spotify:album:..."]}
  {"type":"spotify_unsave",      "uris":["spotify:track:..."]}
  {"type":"discogs_coll_remove", "release_id":123456, "instance_id":789}

Les concerts ne passent pas par ici : le site écrit directement
data/concerts.json, qu'aucun script automatique ne touche.
"""
import os, pathlib, time
from common import DATA, env, http, read_jsonl, append_jsonl

LIB = "https://api.spotify.com/v1/me/library"
DG = "https://api.discogs.com"


def discogs(method, path):
    tok, user = env("DISCOGS_TOKEN"), env("DISCOGS_USER")
    st, r = http(f"{DG}{path.format(user=user)}?token={tok}", method=method,
                 headers={"Authorization": f"Discogs token={tok}"})
    time.sleep(1.1)
    return st in (200, 201, 204), st


def spotify(method, uris):
    from collect_listens import access_token
    st, r = http(LIB, method=method,
                 headers={"Authorization": "Bearer " + access_token()},
                 data={"uris": uris})
    return st in (200, 201, 204), st


def discogs_search(artist, title):
    """Trouve l'ID de pressage vinyle le plus plausible pour artiste + titre."""
    tok = env("DISCOGS_TOKEN")
    import urllib.parse
    q = urllib.parse.urlencode({"artist": artist, "release_title": title,
                                "format": "Vinyl", "type": "release",
                                "sort": "year", "sort_order": "desc",
                                "per_page": 5, "token": tok})
    st, r = http(f"{DG}/database/search?{q}", headers={"Authorization": f"Discogs token={tok}"})
    time.sleep(1.1)
    if st != 200 or not r or not r.get("results"):
        return None
    return r["results"][0].get("id")


def run(a):
    t = a.get("type")
    rid = a.get("release_id")
    if t == "discogs_want_search":
        rid = discogs_search(a.get("artist", ""), a.get("title", ""))
        if not rid:
            return False, "aucun pressage vinyle trouvé"
        return discogs("PUT", f"/users/{{user}}/wants/{rid}")
    if t == "discogs_want_add":
        return discogs("PUT", f"/users/{{user}}/wants/{rid}")
    if t == "discogs_want_remove":
        return discogs("DELETE", f"/users/{{user}}/wants/{rid}")
    if t == "discogs_coll_add":
        return discogs("POST", f"/users/{{user}}/collection/folders/1/releases/{rid}")
    if t == "discogs_coll_search":
        rid = discogs_search(a.get("artist", ""), a.get("title", ""))
        if not rid:
            return False, "aucun pressage vinyle trouvé"
        return discogs("POST", f"/users/{{user}}/collection/folders/1/releases/{rid}")
    if t == "discogs_coll_remove":
        iid = a.get("instance_id")
        if not iid:
            return False, "instance_id manquant"
        return discogs("DELETE",
                       f"/users/{{user}}/collection/folders/{a.get('folder_id', 1)}"
                       f"/releases/{rid}/instances/{iid}")
    if t == "spotify_save":
        return spotify("PUT", a.get("uris", []))
    if t == "spotify_unsave":
        return spotify("DELETE", a.get("uris", []))
    return False, f"type inconnu : {t}"


def main():
    queue = pathlib.Path(DATA / "actions.jsonl")
    actions = read_jsonl(queue)
    if not actions:
        print("  file vide")
        return
    print(f"  {len(actions)} action(s)")
    log = []
    for a in actions:
        try:
            ok, code = run(a)
        except SystemExit as e:
            ok, code = False, str(e)
        print(f"  {'ok ' if ok else 'ÉCHEC'} {a.get('type')} -> {code}")
        log.append({**a, "ok": ok, "code": str(code),
                    "done": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    append_jsonl(DATA / "actions_log.jsonl", log)
    queue.write_text("", encoding="utf-8")   # file vidée, jamais supprimée
    print("  file vidée")


if __name__ == "__main__":
    main()
