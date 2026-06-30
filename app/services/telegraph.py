from __future__ import annotations

from typing import Any
import requests
from bs4 import BeautifulSoup

ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "a", "blockquote", "hr", "h1", "h2", "h3"}


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        attrs = {}
        if tag.name == "a" and tag.get("href"):
            attrs["href"] = tag.get("href")
            attrs["rel"] = "noopener noreferrer"
            attrs["target"] = "_blank"
        tag.attrs = attrs
    return str(soup)


def fetch_content(url: str) -> dict[str, Any]:
    if not url:
        return {"content_html": "", "error": "empty_url"}
    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"content_html": "", "error": str(exc)}
    return {"content_html": clean_html(response.text), "error": None}
