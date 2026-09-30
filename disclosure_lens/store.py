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
    return {**meta, "demo": False, "boilerplate_paragraphs_removed": removed, "summary": summarize(recs), "lexicon": lexicon.density_profile(clean),
            "sentences": [{"d": r["direction"], "m": r["material_neg"]} for r in recs]}


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
