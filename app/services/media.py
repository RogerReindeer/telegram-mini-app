from __future__ import annotations

from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse

import requests

from ..cache import cache_get_or_set, image_cache_ttl
from ..utils import clean_value


_IMAGE_SESSION = requests.Session()
_IMAGE_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; ZefirkinyBaozyMiniApp/1.0)",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
})

_ALLOWED_IMAGE_HOSTS = ("teletype.in", "teletype.media", "telegra.ph")
_MAX_IMAGE_BYTES = 12 * 1024 * 1024
_MAX_REDIRECTS = 3


class ExternalImageError(RuntimeError):
    pass


def _normalized_external_url(value: Any, *, base_url: str = "") -> str:
    text = clean_value(value)
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    absolute = urljoin(base_url, text) if base_url else text
    if absolute.startswith("http://"):
        absolute = "https://" + absolute[len("http://"):]
    return absolute


def _replace_host(url: str, host: str) -> str:
    parsed = urlparse(url)
    return urlunparse(("https", host, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _is_teletype_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return (
        host == "teletype.in"
        or host.endswith(".teletype.in")
        or host == "teletype.media"
        or host.endswith(".teletype.media")
    )


def teletype_mirror_page_url(value: Any) -> str:
    """Translate an old Teletype page URL to the temporary teletype.media mirror.

    The source value is never written back to CRM/Supabase; this is runtime-only
    recovery while the historical .in domain is unavailable.
    """
    text = _normalized_external_url(value)
    if not text:
        return ""
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host in {"teletype.in", "www.teletype.in"}:
        return _replace_host(text, "teletype.media")
    return text


def external_image_candidates(value: Any) -> list[str]:
    """Return safe runtime candidates for a Telegraph/Teletype image.

    Teletype historically stored direct files on img1..imgN.teletype.in.  When
    the .in domain is unavailable, the mirror may expose those files through a
    mirror image host or the main mirror host.  We try mirror candidates first,
    then the original URL so the application self-heals again when .in returns.
    """
    text = _normalized_external_url(value)
    if not text:
        return []

    parsed = urlparse(text)
    host = (parsed.hostname or "").lower().rstrip(".")
    candidates: list[str] = []

    def add(candidate: str) -> None:
        candidate = _normalized_external_url(candidate)
        if candidate and candidate not in candidates and is_allowed_external_image_url(candidate):
            candidates.append(candidate)

    if host == "teletype.in" or host == "www.teletype.in":
        add(_replace_host(text, "teletype.media"))
        add(text)
    elif host.endswith(".teletype.in"):
        subdomain = host[: -len(".teletype.in")]
        if subdomain:
            add(_replace_host(text, f"{subdomain}.teletype.media"))
        # Some mirror deployments serve historical /files/* through the main
        # hostname rather than recreating every old image subdomain.
        add(_replace_host(text, "teletype.media"))
        add(_replace_host(text, "cdn.teletype.media"))
        add(text)
    else:
        add(text)

    return candidates


def is_allowed_external_image_url(value: Any) -> bool:
    text = _normalized_external_url(value)
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_IMAGE_HOSTS)


def external_image_proxy_url(value: Any, *, base_url: str = "") -> str:
    """Return a same-origin URL for Telegraph/Teletype images.

    Keeping upstream URLs in CRM/Supabase while proxying only at render time
    makes media recovery reversible and fixes relative Telegraph `/file/...`
    paths without rewriting source data.
    """
    absolute = _normalized_external_url(value, base_url=base_url)
    if not absolute:
        return ""
    if absolute.startswith("/media/image?"):
        return absolute
    if not is_allowed_external_image_url(absolute):
        return absolute
    return "/media/image?url=" + quote(absolute, safe="")


def _download_one_image_candidate(url: str) -> dict[str, Any]:
    current = _normalized_external_url(url)
    if not is_allowed_external_image_url(current):
        raise ExternalImageError("unsupported_image_host")

    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        host = (parsed.hostname or "").lower()
        headers = {}
        if _is_teletype_host(host):
            # Avoid hotlink/CDN policies tied to the caller's Render domain.
            headers["Referer"] = "https://teletype.media/"

        try:
            response = _IMAGE_SESSION.get(current, timeout=(4, 12), allow_redirects=False, headers=headers)
        except requests.RequestException as exc:
            raise ExternalImageError("image_upstream_unavailable") from exc

        if response.status_code in {301, 302, 303, 307, 308}:
            location = clean_value(response.headers.get("location"))
            next_url = _normalized_external_url(location, base_url=current)
            if not location or not is_allowed_external_image_url(next_url):
                raise ExternalImageError("unsafe_image_redirect")
            current = next_url
            continue

        if response.status_code != 200:
            raise ExternalImageError(f"image_upstream_status_{response.status_code}")

        content_type = clean_value(response.headers.get("content-type")).split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise ExternalImageError("upstream_is_not_image")

        declared_length = clean_value(response.headers.get("content-length"))
        if declared_length:
            try:
                if int(declared_length) > _MAX_IMAGE_BYTES:
                    raise ExternalImageError("image_too_large")
            except ValueError:
                pass

        body = response.content
        if not body or len(body) > _MAX_IMAGE_BYTES:
            raise ExternalImageError("image_too_large" if body else "empty_image")

        return {
            "body": body,
            "content_type": content_type,
            "source_url": current,
        }

    raise ExternalImageError("too_many_image_redirects")


def _download_external_image_uncached(url: str) -> dict[str, Any]:
    candidates = external_image_candidates(url)
    if not candidates:
        raise ExternalImageError("unsupported_image_host")

    last_error: ExternalImageError | None = None
    for candidate in candidates:
        try:
            return _download_one_image_candidate(candidate)
        except ExternalImageError as exc:
            last_error = exc
            continue

    raise last_error or ExternalImageError("image_upstream_unavailable")


def fetch_external_image(url: str) -> dict[str, Any]:
    normalized = _normalized_external_url(url)
    if not is_allowed_external_image_url(normalized):
        raise ExternalImageError("unsupported_image_host")
    return cache_get_or_set(
        f"image:proxy:v244:{normalized}",
        image_cache_ttl(),
        lambda: _download_external_image_uncached(normalized),
        namespace="images",
    )
