"""Fonctions partagées par tous les collecteurs."""
import json, os, pathlib, sys, time, unicodedata, re
import urllib.request, urllib.parse, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site" / "data"
UA = "louis-music-dashboard/1.0 (personnel)"


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        sys.exit(f"[stop] secret manquant : {name}")
    return v


def http(url, method="GET", headers=None, data=None, form=None, retries=3):
    """Requête HTTP avec relances sur 429/5xx. Renvoie (status, objet JSON | None)."""
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", 0) or (2 ** attempt) * 5)
                print(f"  [{e.code}] pause {wait}s puis relance")
                time.sleep(wait)
                continue
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw.decode(errors="replace")[:400]}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep((2 ** attempt) * 3)
                continue
            print(f"  [erreur réseau] {e}")
            return 0, None
    return 0, None


def read_json(path, default):
    p = pathlib.Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [avertissement] {p} illisible ({e}), valeur par défaut utilisée")
        return default


def write_json(path, obj):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  écrit {p.relative_to(ROOT)} ({p.stat().st_size // 1024} Ko)")


def read_jsonl(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def append_jsonl(path, rows):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def all_listens():
    """Toutes les écoutes, tous mois confondus, triées par date."""
    rows = []
    for f in sorted((DATA / "listens").glob("*.jsonl")):
        rows.extend(read_jsonl(f))
    rows.sort(key=lambda r: r.get("ts", ""))
    return rows


def norm(s):
    """Normalisation pour rapprocher les noms entre services."""
    s = str(s or "").lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s*[\(\[][^()\[\]]*\b(deluxe|remaster(ed)?|expanded|anniversary|special|"
               r"bonus|legacy|edition|version|reissue|explicit|mono|stereo)\b[^()\[\]]*[\)\]]", "", s)
    s = re.sub(r"\s*-\s*(\d{4}\s*)?(deluxe|remaster(ed)?|expanded|anniversary|"
               r"special edition|bonus|legacy|mono|stereo|radio edit|single version).*$", "", s)
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)
