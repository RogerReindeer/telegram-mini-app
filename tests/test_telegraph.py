from __future__ import annotations

from app.services.telegraph import render_telegraph_node


def test_telegraph_renderer_drops_script_tag_but_keeps_escaped_text():
    rendered = render_telegraph_node({"tag": "script", "children": ["<unsafe>"]})
    assert rendered == "&lt;unsafe&gt;"
    assert "script" not in rendered


def test_telegraph_renderer_rejects_javascript_href():
    rendered = render_telegraph_node({
        "tag": "a",
        "attrs": {"href": "javascript:alert(1)", "title": "safe"},
        "children": ["open"],
    })
    assert "javascript:" not in rendered
    assert 'title="safe"' in rendered


def test_telegraph_renderer_allows_https_and_proxies_images():
    link = render_telegraph_node({
        "tag": "a", "attrs": {"href": "/page"}, "children": ["page"]
    })
    assert 'href="https://telegra.ph/page"' in link
    image = render_telegraph_node({
        "tag": "img", "attrs": {"src": "/file/example.jpg", "alt": "cover"}
    })
    assert "javascript:" not in image
    assert 'alt="cover"' in image
