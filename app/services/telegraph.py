from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..cache import cache_get_or_set, image_cache_ttl, telegraph_cache_ttl
from .reader import clean_value, split_text_paragraphs

def telegraph_path_from_url(url: str) -> str:
    text = clean_value(url)
    if not text:
        return ""
    text = text.split("?")[0].rstrip("/")
    if "telegra.ph/" in text:
        return text.split("telegra.ph/", 1)[1]
    if "teletype.in/" in text:
        return ""
    return text


def is_probably_direct_image_url(url: Any) -> bool:
    text = clean_value(url)

    if not text:
        return False

    lowered = text.split("?")[0].lower()

    return bool(
        re.search(r"\.(?:png|jpe?g|webp|gif|avif|svg)$", lowered)
        or "teletype.in/files/" in lowered
        or "telegra.ph/file/" in lowered
    )


def extract_first_image_from_html(page_url: str, html_text: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)

        if match:
            src = html.unescape(clean_value(match.group(1)))

            if src:
                return urljoin(page_url, src)

    return ""


def _resolve_external_image_url_uncached(url: Any) -> str:
    """Return a browser-displayable image URL.

    Fox images are stored in the Excel/Google Sheets tab `fox` as Teletype links.
    If the link is already a direct image URL, it is used as-is. If it is a
    Teletype/Telegraph page URL, the first page image is extracted and used.
    """
    text = clean_value(url)

    if not text:
        return ""

    if text.startswith("//"):
        text = f"https:{text}"

    if text.startswith("http://"):
        text = "https://" + text[len("http://"):]

    if is_probably_direct_image_url(text):
        return text

    parsed = urlparse(text)
    host = parsed.netloc.lower()

    if "teletype.in" not in host and "telegra.ph" not in host:
        return text

    try:
        response = requests.get(
            text,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
    except Exception:
        return text

    extracted = extract_first_image_from_html(text, response.text)

    return extracted or text


def resolve_external_image_url(url: Any) -> str:
    text = clean_value(url)
    if not text:
        return ""
    return cache_get_or_set(
        f"image:resolve:{text}",
        image_cache_ttl(),
        lambda: _resolve_external_image_url_uncached(text),
        namespace="images",
    )


def html_to_plain_text(fragment: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", fragment)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_chapter_service_block(fragment: str) -> bool:
    text = html_to_plain_text(fragment)
    normalized = text.lower().replace("ё", "е")

    if not normalized:
        return True

    if normalized in ("--", "—", "–", "***", "* * *"):
        return True

    footer_markers = (
        "перевод зефиркины",
        "перевод: зефиркины",
        "зефиркины баоцы",
        "зефиркины баоцзы",
        "спасибо что читаете с нами",
        "спасибо, что читаете с нами",
        "спасибо что читаете вместе с нами",
        "спасибо, что читаете вместе с нами",
        "купить полный перевод",
        "полный перевод boosty",
        "boosty/telegraph",
        "boosty / telegraph",
        "boosty / teletype",
        "boosty/teletype",
    )

    if any(marker in normalized for marker in footer_markers):
        return True

    # Часто в конце главы есть отдельная ссылка/пункт покупки полного перевода.
    # Удаляем именно короткий служебный блок, а не любое упоминание Boosty внутри текста.
    if len(normalized) <= 220 and ("boosty" in normalized or "telegraph" in normalized or "teletype" in normalized):
        if any(marker in normalized for marker in ("купить", "полный перевод", "подпис", "ранний доступ")):
            return True

    navigation_markers = (
        "к оглавлению",
        "оглавление",
        "следующая глава",
        "следующая",
        "прошлая глава",
        "предыдущая глава",
        "предыдущая",
        "назад",
        "вперед",
        "вперёд",
        "next chapter",
        "previous chapter",
        "contents",
    )

    if len(normalized) <= 160 and any(marker in normalized for marker in navigation_markers):
        return True

    return False


def clean_chapter_content_html(html_content: str) -> str:
    content = clean_value(html_content)

    if not content:
        return ""

    block_pattern = re.compile(
        r"(?is)<(p|h1|h2|h3|h4|blockquote|li|div|a)\b[^>]*>.*?</\1>"
    )

    def replace_block(match: re.Match) -> str:
        block = match.group(0)

        if is_chapter_service_block(block):
            return ""

        return block

    cleaned = block_pattern.sub(replace_block, content)

    # На всякий случай вычищаем хвосты, если они пришли не отдельным <p>, а текстом внутри блока.
    trailing_patterns = (
        r"(?is)<p[^>]*>\s*(?:--|—|–)\s*</p>\s*",
        r"(?is)<p[^>]*>\s*спасибо[, ]+что читаете(?: вместе)? с нами!?\s*(?:💙)?\s*</p>\s*",
        r"(?is)<p[^>]*>\s*перевод\s+зефиркины\s+бао[цз]ы.*?</p>\s*",
        r"(?is)<p[^>]*>.*?купить\s+полный\s+перевод.*?</p>\s*",
        r"(?is)<a[^>]*>.*?купить\s+полный\s+перевод.*?</a>\s*",
    )

    changed = True
    while changed:
        changed = False
        for pattern in trailing_patterns:
            updated = re.sub(pattern, "", cleaned).strip()
            if updated != cleaned:
                cleaned = updated
                changed = True

    cleaned = re.sub(r"(?is)<hr\s*/?>", "", cleaned)
    cleaned = re.sub(r"(?is)(?:\s|&nbsp;)*$", "", cleaned).strip()

    return cleaned


def render_telegraph_node(node: Any) -> str:
    if isinstance(node, str):
        return html.escape(node)
    if not isinstance(node, dict):
        return ""
    tag = clean_value(node.get("tag"))
    if not tag:
        return ""
    attrs = node.get("attrs") or {}
    children = node.get("children") or []
    safe_attrs = []
    if isinstance(attrs, dict):
        for key, value in attrs.items():
            key_text = clean_value(key)
            value_text = clean_value(value)
            if key_text in ("href", "src", "alt", "title"):
                safe_attrs.append(f'{html.escape(key_text)}="{html.escape(value_text)}"')
    attrs_text = f" {' '.join(safe_attrs)}" if safe_attrs else ""
    inner = "".join(render_telegraph_node(child) for child in children)
    if tag in ("br", "img"):
        return f"<{tag}{attrs_text}>"
    return f"<{tag}{attrs_text}>{inner}</{tag}>"


def _fetch_telegraph_content_uncached(url: str) -> tuple[dict | None, str]:
    path = telegraph_path_from_url(url)
    if not path:
        return None, ""
    api_url = f"https://api.telegra.ph/getPage/{quote(path)}"
    try:
        response = requests.get(api_url, params={"return_content": "true"}, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        return None, f"Ошибка загрузки Telegraph: {error}"
    if not data.get("ok"):
        return None, data.get("error") or "Telegraph вернул ошибку."
    result = data.get("result") or {}
    raw_html = "".join(render_telegraph_node(node) for node in result.get("content") or [])
    html_content = clean_chapter_content_html(raw_html)
    return {"title": result.get("title") or "", "content_html": html_content}, ""


def fetch_telegraph_content(url: str) -> tuple[dict | None, str]:
    text = clean_value(url)
    if not text:
        return None, ""
    return cache_get_or_set(
        f"telegraph:content:{text}",
        telegraph_cache_ttl(),
        lambda: _fetch_telegraph_content_uncached(text),
        namespace="telegraph",
    )
