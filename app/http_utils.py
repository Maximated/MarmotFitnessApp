from fastapi import Request


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def safe_next(url: str | None) -> str | None:
    """A `next` query/form param is attacker-controllable -- it's echoed
    straight back into redirects and `href`s across the app. Only accept it
    if it's a same-origin relative path; otherwise it's an open-redirect
    (an absolute URL) or click-through script-execution (`javascript:...`)
    vector, so treat it the same as if `next` had never been given.
    Rejects protocol-relative (`//host/...`) and backslash tricks browsers
    sometimes normalize into `//`."""
    if not url:
        return None
    url = url.strip()
    if not url or "\\" in url or any(c in url for c in ("\t", "\n", "\r")):
        return None
    if not url.startswith("/") or url.startswith("//"):
        return None
    return url
