"""À LANCER UNE SEULE FOIS SUR TA MACHINE (pas dans GitHub Actions).

Récupère le refresh token Spotify, qui est le seul secret à conserver.
À refaire tous les 6 mois : Spotify fait expirer l'autorisation applicative.

    python scripts/auth_spotify.py

Prérequis, dans https://developer.spotify.com/dashboard :
  - créer une application
  - ajouter EXACTEMENT cette Redirect URI : http://127.0.0.1:8974/callback
  - noter le Client ID et le Client Secret
"""
import base64, http.server, json, secrets, sys, threading, time, urllib.parse, webbrowser
from common import http as api  # renommé : 'http' entrerait en conflit avec http.server

REDIRECT = "http://127.0.0.1:8974/callback"
SCOPES = " ".join([
    "user-read-recently-played",     # les 50 dernières écoutes
    "user-read-currently-playing",   # le titre en cours
    "user-library-read",             # titres et albums enregistrés
    "user-library-modify",           # enregistrer / retirer
    "user-follow-read",              # artistes suivis
    "user-follow-modify",            # suivre / ne plus suivre
    "user-top-read",                 # tops par période
])
got = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        got.update({k: v[0] for k, v in q.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = "code" in got
        self.wfile.write(("<h2>" + ("C'est bon, tu peux fermer cet onglet."
                                    if ok else "Échec : " + got.get("error", "?")) + "</h2>").encode())

    def log_message(self, *a):
        pass


def main():
    cid = input("Client ID     : ").strip()
    csec = input("Client Secret : ").strip()
    if not cid or not csec:
        sys.exit("Il faut les deux.")

    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": SCOPES, "state": state, "show_dialog": "true"})

    srv = http.server.HTTPServer(("127.0.0.1", 8974), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    print("\nOuverture du navigateur. Si rien ne s'ouvre, colle cette adresse :\n" + url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    for _ in range(240):
        if got:
            break
        time.sleep(0.5)
    if got.get("state") != state or "code" not in got:
        sys.exit("Autorisation refusée ou expirée.")

    basic = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    st, tok = api("https://accounts.spotify.com/api/token", method="POST",
                   headers={"Authorization": "Basic " + basic},
                   form={"grant_type": "authorization_code", "code": got["code"],
                         "redirect_uri": REDIRECT})
    if st != 200 or not tok or "refresh_token" not in tok:
        sys.exit(f"Échec de l'échange ({st}) : {json.dumps(tok)[:300]}")

    print("\n" + "=" * 62)
    print("Ajoute ces trois secrets dans GitHub")
    print("(dépôt > Settings > Secrets and variables > Actions > New secret)")
    print("=" * 62)
    print(f"SPOTIFY_CLIENT_ID     = {cid}")
    print(f"SPOTIFY_CLIENT_SECRET = {csec}")
    print(f"SPOTIFY_REFRESH_TOKEN = {tok['refresh_token']}")
    print("=" * 62)
    print("Ne commite jamais ces valeurs dans le dépôt.")


if __name__ == "__main__":
    main()
