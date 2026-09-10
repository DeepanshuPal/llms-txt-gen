"""Polite site crawler for llms.txt generation.

Discovers pages through robots.txt + XML sitemaps (never brute-force link
walking), fetches a capped sample, and annotates each URL with its <title>
and meta description. Respects robots.txt disallow rules throughout.
"""

from __future__ import annotations

import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

DEFAULT_UA = "llms-txt-gen/1.0 (+https://github.com/DeepanshuPal/llms-txt-gen)"

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class Page:
    url: str
    title: str = ""
    description: str = ""


@dataclass
class CrawlResult:
    base_url: str
    home_title: str = ""
    home_description: str = ""
    products: list[Page] = field(default_factory=list)
    collections: list[Page] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    articles: list[Page] = field(default_factory=list)
    policies: list[Page] = field(default_factory=list)
    products_json_ok: bool = False
    robots_found: bool = False
    robots_disallowed_root: bool = False
    skipped_by_robots: int = 0
    sitemaps_used: list[str] = field(default_factory=list)


class _MetaProbe(HTMLParser):
    """Pull <title> and <meta name=description> out of a page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or "").lower() == "description":
            if a.get("content") and not self.description:
                self.description = a["content"].strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def _get(session, url, timeout):
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def _sitemap_urls(xml_text: str):
    """Return (kind, urls) where kind is 'index' or 'urlset'."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None, []
    tag = root.tag.replace(SITEMAP_NS, "")
    if tag == "sitemapindex":
        locs = [el.text for el in root.iter(SITEMAP_NS + "loc") if el.text]
        return "index", locs
    if tag == "urlset":
        locs = [el.text for el in root.iter(SITEMAP_NS + "loc") if el.text]
        return "urlset", locs
    return None, []


def _categorize(url: str) -> str:
    path = urlparse(url).path.lower()
    if "/products/" in path:
        return "products"
    if "/collections/" in path or "/category/" in path or "/collections" == path.rstrip("/"):
        return "collections"
    if "/blogs/" in path or "/articles/" in path:
        return "articles"
    if "/policies/" in path or "/policy" in path:
        return "policies"
    return "pages"


class Crawler:
    def __init__(self, base_url: str, delay: float = 0.4, timeout: int = 20,
                 user_agent: str = DEFAULT_UA):
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url
        self.base = base_url.rstrip("/")
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.robots = urllib.robotparser.RobotFileParser()
        self.result = CrawlResult(base_url=self.base)

    def _pause(self):
        if self.delay > 0:
            time.sleep(self.delay)

    def _allowed(self, url: str) -> bool:
        if not self.result.robots_found:
            return True
        ok = self.robots.can_fetch(DEFAULT_UA, url)
        if not ok:
            self.result.skipped_by_robots += 1
        return ok

    def load_robots(self):
        resp = _get(self.session, self.base + "/robots.txt", self.timeout)
        if resp is None or "user-agent" not in resp.text.lower():
            return []
        self.result.robots_found = True
        self.robots.parse(resp.text.splitlines())
        # blanket block of everything?
        self.result.robots_disallowed_root = not self.robots.can_fetch(
            DEFAULT_UA, self.base + "/")
        import re
        return re.findall(r"(?im)^sitemap:\s*(\S+)", resp.text)

    def annotate(self, page: Page):
        """Fetch a page and fill in title/description."""
        if not self._allowed(page.url):
            return False
        self._pause()
        resp = _get(self.session, page.url, self.timeout)
        if resp is None or "text/html" not in resp.headers.get("Content-Type", ""):
            return False
        probe = _MetaProbe()
        probe.feed(resp.text[:200_000])  # head of the doc is enough for title/meta
        page.title = probe.title
        page.description = probe.description
        return True

    def crawl(self, max_products=12, max_collections=20, max_pages=15,
              max_articles=5):
        # 1. robots.txt
        sitemap_seeds = self.load_robots()
        if self.result.robots_disallowed_root:
            return self.result  # nothing more we may do

        # 2. homepage
        home = Page(self.base)
        if self.annotate(home):
            self.result.home_title = home.title
            self.result.home_description = home.description

        # 3. products.json probe (Shopify)
        self._pause()
        pj = _get(self.session, self.base + "/products.json?limit=1", self.timeout)
        if pj is not None:
            try:
                self.result.products_json_ok = isinstance(pj.json().get("products"), list)
            except ValueError:
                pass

        # 4. sitemaps: robots-declared first, conventional fallback
        candidates = sitemap_seeds or [self.base + "/sitemap.xml"]
        url_entries: list[str] = []
        for sm in candidates:
            self._pause()
            resp = _get(self.session, sm, self.timeout)
            if resp is None:
                continue
            kind, locs = _sitemap_urls(resp.text)
            if kind == "urlset":
                self.result.sitemaps_used.append(sm)
                url_entries.extend(locs)
            elif kind == "index":
                self.result.sitemaps_used.append(sm)
                for child in locs:
                    # prioritize catalog-bearing sub-sitemaps
                    self._pause()
                    cresp = _get(self.session, child, self.timeout)
                    if cresp is None:
                        continue
                    ckind, clocs = _sitemap_urls(cresp.text)
                    if ckind == "urlset":
                        self.result.sitemaps_used.append(child)
                        url_entries.extend(clocs)
            if url_entries:
                break  # first working sitemap source wins

        # 5. bucket + cap
        buckets = {"products": [], "collections": [], "pages": [],
                   "articles": [], "policies": []}
        seen = set()
        for u in url_entries:
            if u in seen:
                continue
            seen.add(u)
            buckets[_categorize(u)].append(Page(u))
        caps = {"products": max_products, "collections": max_collections,
                "pages": max_pages, "articles": max_articles,
                "policies": 6}
        for name, cap in caps.items():
            picked = buckets[name][:cap]
            kept = []
            for p in picked:
                if self.annotate(p):
                    kept.append(p)
            setattr(self.result, name, kept)

        # 6. Shopify policy pages are often missing from sitemaps - probe the
        #    standard paths if the bucket came up empty.
        if not self.result.policies:
            for slug in ("refund-policy", "privacy-policy", "shipping-policy",
                         "terms-of-service"):
                url = f"{self.base}/policies/{slug}"
                if not self._allowed(url):
                    continue
                self._pause()
                resp = _get(self.session, url, self.timeout)
                if resp is not None:
                    p = Page(url)
                    probe = _MetaProbe()
                    probe.feed(resp.text[:200_000])
                    p.title = probe.title or slug.replace("-", " ").title()
                    p.description = probe.description
                    self.result.policies.append(p)

        return self.result
