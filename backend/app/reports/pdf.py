"""HTML templates (Jinja2) -> PDF through headless Chromium.

Chromium shapes Arabic and lays out RTL correctly, which is why it was chosen over
WeasyPrint (design doc section 7). Fonts are embedded as data URIs so the output
does not depend on the fonts installed on the server.

In production this runs in the background worker, never inside a web request.
"""
import base64
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).parent
_env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))

# (file, weight, unicode-range) - Arabic and Latin subsets of IBM Plex Sans Arabic (SIL OFL)
_FONTS = [
    ("ibm-plex-sans-arabic-arabic-{w}-normal.woff2", "U+0600-06FF,U+0750-077F,U+0870-08FF,U+FB50-FDFF,U+FE70-FEFF,U+200C-200E"),
    ("ibm-plex-sans-arabic-latin-{w}-normal.woff2", "U+0000-00FF,U+2000-206F,U+20AC,U+2122,U+2212"),
]


@lru_cache
def font_css() -> str:
    rules = []
    for weight in (400, 600, 700):
        for pattern, urange in _FONTS:
            data = base64.b64encode((HERE / "fonts" / pattern.format(w=weight)).read_bytes()).decode()
            rules.append(
                "@font-face{font-family:'Plex Arabic';font-style:normal;"
                f"font-weight:{weight};src:url(data:font/woff2;base64,{data}) format('woff2');"
                f"unicode-range:{urange};}}"
            )
    return "\n".join(rules)


def render_html(template: str, **context) -> str:
    return _env.get_template(template).render(font_css=font_css(), **context)


def html_to_pdf(html: str, *, footer_text: str = "", landscape: bool = False) -> bytes:
    from playwright.sync_api import sync_playwright

    footer = (
        "<div style=\"font-size:8px;width:100%;padding:0 12mm;display:flex;justify-content:space-between;"
        "color:#666;font-family:sans-serif\"><span>" + footer_text + "</span>"
        "<span><span class=\"pageNumber\"></span> / <span class=\"totalPages\"></span></span></div>"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            return page.pdf(
                format="A4", landscape=landscape, print_background=True, display_header_footer=True,
                header_template="<span></span>", footer_template=footer,
                margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
            )
        finally:
            browser.close()
