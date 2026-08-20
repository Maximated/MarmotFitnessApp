import time
from pathlib import Path

import httpx

GIT_DIR = Path("/code/.git")

GITHUB_REPO = "Maximated/MarmotFitnessApp"
GITHUB_BRANCH = "main"
REMOTE_CACHE_TTL_SECONDS = 600

_current_commit_cache: str | None = None
_current_commit_fetched = False
_remote_commit_cache: dict = {}


def get_current_commit() -> str | None:
    """The commit this running instance is actually serving -- read live
    from the repo's .git directory (mounted read-only into the container)
    rather than baked in at build time, since this project deploys by
    `git pull` + restart, with no separate build/release step. Parses the
    .git files directly instead of shelling out to `git`, which isn't
    installed in the (deliberately slim) app image."""
    global _current_commit_cache, _current_commit_fetched
    if _current_commit_fetched:
        return _current_commit_cache
    _current_commit_fetched = True
    try:
        head = (GIT_DIR / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            ref_path = head.removeprefix("ref:").strip()
            _current_commit_cache = (GIT_DIR / ref_path).read_text().strip()
        else:
            _current_commit_cache = head
    except OSError:
        pass
    return _current_commit_cache


def get_latest_remote_commit() -> str | None:
    """The tip of the repo's main branch on GitHub. Cached for a while so
    a page a single user loads often doesn't hammer the GitHub API; falls
    back to the last known value if a refresh fails."""
    now = time.monotonic()
    cached_at = _remote_commit_cache.get("at")
    if cached_at is not None and now - cached_at < REMOTE_CACHE_TTL_SECONDS:
        return _remote_commit_cache.get("sha")
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}",
            timeout=3.0,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        sha = response.json()["sha"]
    except Exception:
        return _remote_commit_cache.get("sha")
    _remote_commit_cache["sha"] = sha
    _remote_commit_cache["at"] = now
    return sha


def get_version_status() -> dict:
    current = get_current_commit()
    latest = get_latest_remote_commit()
    return {
        "current_short": current[:7] if current else None,
        "up_to_date": current is None or latest is None or current == latest,
    }
