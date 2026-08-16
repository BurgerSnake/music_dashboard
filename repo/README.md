# Tableau de bord musique

Historique d'écoute, bibliothèque, vinyles, sorties d'albums et concerts,
dans un dépôt GitHub qui se met à jour tout seul. Aucun serveur.

- Une Action toutes les 30 min récupère les écoutes Spotify et les archive.
- Une Action quotidienne synchronise bibliothèque, Discogs, sorties et concerts.
- Le site est une page statique publiée par GitHub Pages.
- Les écritures depuis le site (ajouter un concert, mettre un disque en wantlist)
  passent par un commit, qui déclenche une Action qui détient les secrets.

```
data/listens/AAAA-MM.jsonl   écoutes brutes, une par ligne     ← écrit par l'Action
data/library.json            likes, albums, artistes suivis    ← écrit par l'Action
data/vinyl.json              collection + wantlist Discogs     ← écrit par l'Action
data/releases.json           sorties MusicBrainz               ← écrit par l'Action
data/events.json             concerts Ticketmaster             ← écrit par l'Action
data/concerts.json           TES concerts                      ← écrit par toi / le site
data/actions.jsonl           file d'attente des demandes       ← écrit par le site
site/data/dashboard.json     tout l'agrégé pour la page        ← recalculé à chaque fois
```

---

## Qui fait quoi

**Ce que le dépôt fait tout seul :** collecte, agrégation, calculs, publication.

**Ce que tu dois faire une fois :** créer le dépôt, obtenir cinq identifiants,
les coller dans les secrets GitHub, activer Pages. Compte 30 minutes.

**Ce que tu dois refaire tous les 6 mois :** relancer `auth_spotify.py`.
L'autorisation applicative Spotify expire, et rien ne te préviendra.

---

## Mise en route

### 1. Le dépôt

Crée un dépôt **privé** sur GitHub, puis :

```bash
git clone https://github.com/TON_USER/TON_DEPOT.git
cd TON_DEPOT
# copie ici tout le contenu de ce dossier
git add . && git commit -m "squelette" && git push
```

### 2. Amorcer avec ton historique

Mets ton export Spotify et ton fichier de concerts dans un dossier, puis :

```bash
pip install openpyxl
python scripts/bootstrap_import.py ~/Downloads/mon_export_spotify
python scripts/build_site.py
git add data site/data && git commit -m "historique" && git push
```

Le dossier doit contenir `Streaming_History_Audio_*.json`, et si tu les as
`YourLibrary.json` et `Concerts*.xlsx`.

### 3. Les identifiants

| Secret | Où l'obtenir |
|---|---|
| `SPOTIFY_CLIENT_ID` `SPOTIFY_CLIENT_SECRET` `SPOTIFY_REFRESH_TOKEN` | `python scripts/auth_spotify.py` (voir ci-dessous) |
| `DISCOGS_TOKEN` | Discogs → Settings → Developers → *Generate token* |
| `DISCOGS_USER` | ton nom d'utilisateur Discogs |
| `TICKETMASTER_KEY` | developer.ticketmaster.com → créer une app (gratuit) |
| `LISTENBRAINZ_TOKEN` | listenbrainz.org → Settings (facultatif mais recommandé) |

Pour Spotify : crée une app sur developer.spotify.com/dashboard, ajoute
**exactement** `http://127.0.0.1:8974/callback` comme Redirect URI, puis lance
`python scripts/auth_spotify.py` et suis les instructions. Le script affiche
les trois valeurs à coller.

⚠️ Depuis février 2026, une app Spotify en Development Mode ne fonctionne que
si son propriétaire a un abonnement **Premium actif**. Le jour où tu résilies,
la collecte Spotify s'arrête — d'où l'intérêt d'envoyer aussi vers ListenBrainz.

Colle chaque valeur dans **Settings → Secrets and variables → Actions → New repository secret**.

### 4. Activer

- **Settings → Actions → General** : *Workflow permissions* → **Read and write**.
- **Settings → Pages** : *Source* → **GitHub Actions**.
- Onglet **Actions** : lance `Synchro quotidienne` à la main pour vérifier.

### 5. Écrire depuis le site

Crée un **fine-grained token** (GitHub → Settings → Developer settings →
Fine-grained tokens) limité à ce seul dépôt, permission **Contents: Read and write**,
avec une expiration courte. Colle-le dans l'onglet *Réglages* du site avec
`ton_user/ton_depot`. Il reste dans le navigateur.

---

## Réglages utiles

Dans `.github/workflows/daily.yml` :

```yaml
HOME_LAT: "50.4108"   # d'où l'on cherche les concerts
HOME_LON: "4.4446"
RADIUS_KM: "350"
```

Dans `scripts/build_site.py` : `MIN_MS = 30000` (durée minimale d'une écoute).
Dans `scripts/fetch_releases.py` et `fetch_events.py` : `TOP_N`, le nombre
d'artistes suivis. Plus haut = plus complet et plus lent.

---

## Ce qui peut casser, et ce que ça donne

| Symptôme | Cause | Correctif |
|---|---|---|
| `refresh token refusé` | autorisation Spotify expirée (6 mois) ou Premium résilié | relancer `auth_spotify.py` |
| écoutes manquantes | plus de 50 titres entre deux passages | passer le cron à `*/20` |
| Discogs 429 | trop d'appels | déjà espacé d'1,1 s, ne pas paralléliser |
| sorties vides | MusicBrainz n'a pas reconnu un artiste | voir `data/mbid_cache.json`, une entrée `null` = non trouvé |
| doublons de concerts | même artiste, même date | `data/concerts.json` s'édite à la main |

Les étapes de la synchro quotidienne sont en `continue-on-error` : si Discogs
tombe, le reste passe quand même.

---

## Vérifier en local

```bash
python scripts/build_site.py
cd site && python -m http.server 8000   # puis http://localhost:8000
```

Le site fonctionne en lecture seule sans jeton, y compris hors ligne.
