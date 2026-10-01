"""Build and save database records (analysis results only, not the full document text)."""
import json
import re
from pathlib import Path

from . import lexicon
from .checks import strip_boilerplate
from .metrics import annotate, summarize
from .preprocess import parse_document


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")


def filename(meta: dict) -> str:
    return f'{_slug(meta["ticker"]).upper()}_{_slug(meta["period"])}_{_slug(meta["filing_type"]).lower()}.json'


def build_record(text: str, meta: dict) -> dict:
    clean, removed = strip_boilerplate(text)
    recs = annotate(parse_document(clean))
    return {**meta, "demo": False, "source_text": text, "boilerplate_paragraphs_removed": removed, "summary": summarize(recs), "lexicon": lexicon.density_profile(clean),
            "sentences": [{"i": r["index"], "t": r["text"], "d": r["direction"], "m": r["material_neg"],
                   "tone": round(r["tone"], 3), "h": round(r["hedge_density"], 4), "hits": r["hits"]} for r in recs]}


def save_record(record: dict, folder: str = "database", overwrite: bool = False) -> Path:
    path = Path(folder) / filename(record)
    if path.exists() and not overwrite:
        raise FileExistsError(path.name)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=1))
    return path


def load_records(folder: str = "database") -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(Path(folder).glob("*.json"))]


def publish_record(record: dict, overwrite: bool = False, secrets: dict | None = None):
    """Live site: commit the file to GitHub (the site redeploys itself). Local run: write to database/."""
    secrets = secrets or {}
    token, repo = secrets.get("GITHUB_TOKEN"), secrets.get("GITHUB_REPO")
    if not (token and repo):
        return "local", save_record(record, overwrite=overwrite).name
    import base64

    import requests
    branch = secrets.get("GITHUB_BRANCH", "main")
    url = f"https://api.github.com/repos/{repo}/contents/database/{filename(record)}"
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    g = requests.get(url, headers=h, params={"ref": branch}, timeout=20)
    sha = g.json().get("sha") if g.status_code == 200 else None
    if sha and not overwrite:
        raise FileExistsError(filename(record))
    body = {"message": f"Add {filename(record)}", "branch": branch,
            "content": base64.b64encode(json.dumps(record, indent=1).encode()).decode()}
    if sha:
        body["sha"] = sha
    requests.put(url, headers=h, json=body, timeout=30).raise_for_status()
    return "github", filename(record)


# ---------- owner tools: list, edit, delete ----------
def list_entries(folder: str = "database") -> list:
    return [(p.name, json.loads(p.read_text())) for p in sorted(Path(folder).glob("*.json"))]


def _gh(secrets):
    t, repo = (secrets or {}).get("GITHUB_TOKEN"), (secrets or {}).get("GITHUB_REPO")
    if not (t and repo):
        return None
    return {"repo": repo, "branch": secrets.get("GITHUB_BRANCH", "main"),
            "h": {"Authorization": f"Bearer {t}", "Accept": "application/vnd.github+json"}}


def _url(g, name):
    return f"https://api.github.com/repos/{g['repo']}/contents/database/{name}"


def _sha(g, name):
    import requests
    r = requests.get(_url(g, name), headers=g["h"], params={"ref": g["branch"]}, timeout=20)
    return r.json().get("sha") if r.status_code == 200 else None


def delete_record(name: str, secrets=None):
    g = _gh(secrets)
    if not g:
        Path("database", name).unlink()
        return
    import requests
    sha = _sha(g, name)
    if not sha:
        raise FileNotFoundError(name)
    requests.delete(_url(g, name), headers=g["h"], timeout=30,
                    json={"message": f"Remove {name}", "sha": sha, "branch": g["branch"]}).raise_for_status()


def update_record(old_name: str, record: dict, secrets=None) -> str:
    """Save an edited record. If the ticker/period/type changed, the file is renamed (old one removed)."""
    new_name = filename(record)
    g = _gh(secrets)
    if not g:
        if new_name != old_name and Path("database", new_name).exists():
            raise FileExistsError(new_name)
        save_record(record, overwrite=True)
        if new_name != old_name:
            Path("database", old_name).unlink(missing_ok=True)
        return new_name
    import base64

    import requests
    sha = _sha(g, new_name)
    if sha and new_name != old_name:
        raise FileExistsError(new_name)
    body = {"message": f"Edit {new_name}", "branch": g["branch"],
            "content": base64.b64encode(json.dumps(record, indent=1).encode()).decode()}
    if sha:
        body["sha"] = sha
    requests.put(_url(g, new_name), headers=g["h"], json=body, timeout=30).raise_for_status()
    if new_name != old_name:
        delete_record(old_name, secrets)
    return new_name
