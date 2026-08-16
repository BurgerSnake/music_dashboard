"""Récupère les écoutes Spotify depuis le dernier passage et les archive.

Tourne toutes les 30 minutes. 50 titres ~= 2 h 45 d'écoute continue,
donc aucune perte même sur une grosse journée.

Écrit  : data/listens/AAAA-MM.jsonl  (une écoute par ligne)
         data/state.json             (curseur du dernier passage)
Envoie : ListenBrainz, si LISTENBRAINZ_TOKEN est défini.
"""
import base64, datetime as dt, os, sys
from common import DATA, env, http, read_json, write_json, read_jsonl, append_jsonl

TOKEN_URL = "https://accounts.spotify.com/api/token"
RECENT = "https://api.spotify.com/v1/me/player/recently-played?limit=50"
LB_SUBMIT = "https://api.listenbrainz.org/1/submit-listens"


def access_token():
    basic = base64.b64encode(
        f"{env('SPOTIFY_CLIENT_ID')}:{env('SPOTIFY_CLIENT_SECRET')}".encode()).decode()
    st, t = http(TOKEN_URL, method="POST", headers={"Authorization": "Basic " + basic},
                 form={"grant_type": "refresh_token",
                       "refresh_token": env("SPOTIFY_REFRESH_TOKEN")})
    if st != 200 or not t:
        sys.exit("[stop] refresh token refusé. L'autorisation Spotify expire tous les 6 mois "
                 "— relance scripts/auth_spotify.py et remets à jour SPOTIFY_REFRESH_TOKEN.")
    return t["access_token"]


def to_listen(item):
    tr = item.get("track") or {}
    if not tr.get("name"):
        return None
    al = tr.get("album") or {}
    return {
        "ts": item["played_at"],
        "track": tr["name"],
        "artist": (tr.get("artists") or [{}])[0].get("name", ""),
        "artists": [a.get("name", "") for a in tr.get("artists") or []],
        "album": al.get("name", ""),
        "ms": tr.get("duration_ms", 0),
        "uri": tr.get("uri", ""),
        "album_uri": al.get("uri", ""),
        "src": "spotify",
    }


def push_listenbrainz(rows):
    tok = os.environ.get("LISTENBRAINZ_TOKEN", "").strip()
    if not tok or not rows:
        return
    payload = [{
        "listened_at": int(dt.datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).timestamp()),
        "track_metadata": {
            "artist_name": r["artist"], "track_name": r["track"], "release_name": r["album"],
            "additional_info": {"submission_client": "louis-dashboard",
                                "music_service": "spotify.com",
                                "duration_ms": r["ms"], "spotify_id": r["uri"]},
        }} for r in rows]
    for i in range(0, len(payload), 50):
        st, _ = http(LB_SUBMIT, method="POST",
                     headers={"Authorization": "Token " + tok},
                     data={"listen_type": "import", "payload": payload[i:i + 50]})
        print(f"  ListenBrainz : lot de {len(payload[i:i+50])} -> statut {st}")


def main():
    state = read_json(DATA / "state.json", {})
    last = state.get("last_played_at", "")

    url = RECENT
    if state.get("after_ms"):
        url += f"&after={state['after_ms']}"
    st, res = http(url, headers={"Authorization": "Bearer " + access_token()})
    if st != 200 or not res:
        sys.exit(f"[stop] recently-played a répondu {st}")

    items = res.get("items", [])
    print(f"  {len(items)} entrées renvoyées par Spotify")
    if not items:
        return

    rows = [r for r in (to_listen(i) for i in items) if r]
    rows = [r for r in rows if r["ts"] > last]          # anti-doublon par horodatage
    rows.sort(key=lambda r: r["ts"])
    if not rows:
        print("  rien de nouveau")
        return

    # dédoublonnage de sécurité contre ce qui est déjà sur le disque
    by_month = {}
    for r in rows:
        by_month.setdefault(r["ts"][:7], []).append(r)
    added = 0
    for month, batch in by_month.items():
        path = DATA / "listens" / f"{month}.jsonl"
        known = {x["ts"] for x in read_jsonl(path)}
        fresh = [r for r in batch if r["ts"] not in known]
        if fresh:
            append_jsonl(path, fresh)
            added += len(fresh)
            print(f"  +{len(fresh)} dans {month}.jsonl")

    newest = rows[-1]["ts"]
    state["last_played_at"] = newest
    state["after_ms"] = int(dt.datetime.fromisoformat(
        newest.replace("Z", "+00:00")).timestamp() * 1000)
    state["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    write_json(DATA / "state.json", state)

    if added:
        push_listenbrainz(rows)


if __name__ == "__main__":
    main()
