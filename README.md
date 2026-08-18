# Tableau de bord musique

Historique d'écoute, bibliothèque, vinyles, sorties d'albums et concerts,
dans un dépôt GitHub qui se met à jour tout seul. Aucun serveur.

Chaque collecteur a sa propre cadence, choisie selon la vitesse à laquelle
la donnée bouge réellement :

| Workflow | Quand | Durée | Ce qu'il fait |
|---|---|---|---|
| **Recalculer le site** | à la demande | ~30 s | rien d'autre que `build_site.py` — **c'est celui à lancer après un changement de code** |
| Écoutes | toutes les 30 min | ~1 min | écoutes Spotify + envoi ListenBrainz |
| Synchro quotidienne | 4h20 | ~1-2 min | bibliothèque Spotify + vinyles Discogs |
| Sorties | lundi et jeudi | ~3 min | MusicBrainz |
| Genres | samedi | ~8 min | familles de genres depuis MusicBrainz |
| Images | le 1er du mois | ~4 min | photos et pochettes Deezer |
- Le site est une page statique publiée par GitHub Pages.
- Les écritures depuis le site (ajouter un concert, mettre un disque en wantlist)
  passent par un commit, qui déclenche une Action qui détient les secrets.

```
data/listens/AAAA-MM.jsonl   écoutes brutes, une par ligne     ← écrit par l'Action
data/images.json             photos et pochettes (cache)       ← écrit par l'Action
data/genres.json             famille de genre par artiste      ← écrit par l'Action
data/library.json            likes, albums, artistes suivis    ← écrit par l'Action
data/vinyl.json              collection + wantlist Discogs     ← écrit par l'Action
data/releases.json           sorties MusicBrainz               ← écrit par l'Action
data/events.json             concerts Ticketmaster             ← écrit par l'Action
data/concerts.json           TES concerts                      ← écrit par toi / le site
data/actions.jsonl           file d'attente des demandes       ← écrit par le site
site/data/dashboard.json     tout l'agrégé pour la page        ← recalculé à chaque fois
site/data/matrix.json        matrice jour × artiste/album      ← chargée à la demande seulement
site/data/matrix_tracks.json matrice jour × titre              ← chargée à la demande seulement
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
| `BANDSINTOWN_APP_ID` | profil Bandsintown for Artists → Settings → General → *Get API Key*. Sans profil artiste, il faut le demander via artists.bandsintown.com/support et attendre l'accord. Peut rester vide : Ticketmaster tourne seul. |
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

Dans `scripts/fetch_releases.py` :
- `TOP_N` — artistes surveillés (120)
- `STALE_DAYS` — un artiste n'est réinterrogé que tous les 10 jours
- `MAX_CALLS` — plafond d'appels par passage (70), ce qui borne la durée

Dans `scripts/fetch_images.py` : `MAX_NEW` (400) — plafond de recherches par
passage. Ce qui dépasse est repris au passage suivant, rien n'est perdu.

Dans `scripts/fetch_events.py` : `TOP_N`, et le geohash calculé depuis
`HOME_LAT` / `HOME_LON`.

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

## Les périodes

Les fenêtres préréglées (24 h, 7 j, 30 j, 6 mois, 1 an, tout) sont calculées
par `build_site.py` en **jours calendaires locaux**, pas en heures glissantes.
La période personnalisée, elle, se calcule dans le navigateur depuis
`matrix.json` — une matrice creuse jour × artiste et jour × album, chargée
seulement quand tu ouvres cet écran. Les deux chemins donnent exactement les
mêmes chiffres, ce qui est vérifiable : choisis « du J-29 à aujourd'hui » et tu
retrouves les valeurs de l'onglet « 30 jours ».

Les titres vivent dans `matrix_tracks.json`, un troisième fichier chargé
seulement si tu ouvres l'onglet Titres sur une plage libre — il est plus gros
que les deux autres réunis.

Granularité de la courbe, choisie automatiquement : heures sur 24 h, jours
jusqu'à 45 jours, semaines jusqu'à 220 jours, mois jusqu'à 1 000 jours, années
au-delà.

## Pourquoi il n'y a pas d'onglet « concerts à proximité »

Il en a existé un, alimenté par Ticketmaster. Il a été retiré, parce
qu'aucune source ouverte ne couvre assez de salles pour être utile :
Bandsintown réserve ses clés aux artistes, Songkick a suspendu les nouvelles
demandes, Spotify n'expose pas sa page Concerts, et Ticketmaster ne connaît
que son propre inventaire — il ratait Manchester, Courtrai et la plupart des
salles belges indépendantes.

Une liste partielle est pire qu'aucune liste : elle laisse croire qu'on a
regardé. Mieux vaut découvrir les concerts ailleurs et les saisir ici.

`scripts/fetch_events.py` reste dans le dépôt, dormant. Pistes si ça change :
UiTdatabank pour la Flandre et Bruxelles, un collecteur par salle (iCal,
JSON:API, HTML), Skiddle pour le Royaume-Uni.

## Les genres

`fetch_genres.py` interroge les genres et tags MusicBrainz, puis les range dans
16 familles lisibles définies en haut du script. **L'ordre de cette liste
compte** : elle va du plus spécifique au plus générique, sinon
« Indie / Alternative » aspirerait tout ce qui porte le tag `alternative rock`.
Pour reclasser un artiste, ajuste les mots-clés d'une famille et supprime son
entrée dans `data/genres.json`.

Les artistes sans tag exploitable restent non classés ; le tableau de bord
affiche le taux de couverture sous la barre des genres pour que tu saches à
quel point la répartition est représentative.

## Vérifier en local

```bash
python scripts/build_site.py
cd site && python -m http.server 8000   # puis http://localhost:8000
```

Le site fonctionne en lecture seule sans jeton, y compris hors ligne.
