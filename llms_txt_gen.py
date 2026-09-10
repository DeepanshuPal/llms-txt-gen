#!/usr/bin/env python3
"""llms-txt-gen: generate a clean llms.txt for any ecommerce store.

Crawls the store politely (robots.txt first, sitemap-driven, rate-limited)
and emits an llms.txt following the llmstxt.org format: store identity up
top, then link sections an agent can actually use - collections, products,
pages, policies, and machine-readable endpoints.

Usage:
    python3 llms_txt_gen.py <store-url> [-o llms.txt] [--max-products N]

Example:
    python3 llms_txt_gen.py https://www.allbirds.com -o llms.txt
"""

from __future__ import annotations

import argparse
import re
import sys

from crawler import Crawler, CrawlResult, Page


def _norm(s: str) -> str:
    return re.sub(r"[®™]", "", s).strip().lower()


def clean_title(title: str, store_name: str) -> str:
    """Strip store-name boilerplate and SEO cruft from a page title."""
    t = title.strip()
    store_words = set(_norm(store_name).split())
    for sep in (" | ", " – ", " — ", " - ", " :: "):
        if sep in t:
            parts = [p.strip() for p in t.split(sep)]
            parts = [p for p in parts
                     if p and _norm(p) != _norm(store_name)
                     and not (len(_norm(p).split()) == 1
                              and _norm(p) in store_words)]
            if parts:
                t = parts[0] if len(parts) == 1 else sep.join(parts)
            break
    return re.sub(r"\s+", " ", t).strip()


def store_name_from(res: CrawlResult) -> str:
    if res.home_title:
        t = res.home_title
        for sep in (" | ", " – ", " — ", " - ", " :: ", ":"):
            if sep in t:
                cand = t.split(sep)[0].strip()
                if 2 <= len(cand) <= 40:
                    return cand
        if 2 <= len(t) <= 40:
            return t
    host = re.sub(r"^www\.", "", res.base_url.split("//", 1)[1]).split(".")[0]
    return host.capitalize()


def one_line(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def section(name: str, pages: list[Page], store: str, annotate=True) -> list[str]:
    if not pages:
        return []
    lines = [f"## {name}", ""]
    for p in pages:
        title = clean_title(p.title, store) or p.url
        if annotate and p.description:
            lines.append(f"- [{title}]({p.url}): {one_line(p.description, 140)}")
        else:
            lines.append(f"- [{title}]({p.url})")
    lines.append("")
    return lines


def render(res: CrawlResult) -> str:
    store = store_name_from(res)
    out = [f"# {store}", ""]
    if res.home_description:
        out.append(f"> {one_line(res.home_description, 240)}")
        out.append("")
    out.append(f"{store} is an ecommerce store at {res.base_url}. "
               "This file orients AI shopping and answer agents: what the "
               "store sells, where the catalog lives, and which pages carry "
               "policies and support information.")
    out.append("")

    out += section("Collections", res.collections, store)
    out += section("Products", res.products, store)
    out += section("Information", res.pages, store)
    if res.articles:
        out += section("Guides and articles", res.articles, store)
    out += section("Policies", res.policies, store)

    if res.products_json_ok:
        out += ["## Machine-readable endpoints", "",
                f"- [Product catalog (JSON)]({res.base_url}/products.json): "
                "full catalog with variants, prices and availability; "
                "paginate with ?page=N&limit=250", ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate an llms.txt for an ecommerce store.")
    ap.add_argument("url", help="Store URL, e.g. https://www.allbirds.com")
    ap.add_argument("-o", "--output", help="Write here instead of stdout")
    ap.add_argument("--max-products", type=int, default=12,
                    help="Product links to include (default 12)")
    ap.add_argument("--max-collections", type=int, default=20)
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--max-articles", type=int, default=5)
    ap.add_argument("--delay", type=float, default=0.4,
                    help="Seconds between requests (default 0.4)")
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    crawler = Crawler(args.url, delay=args.delay, timeout=args.timeout)
    res = crawler.crawl(max_products=args.max_products,
                        max_collections=args.max_collections,
                        max_pages=args.max_pages,
                        max_articles=args.max_articles)

    if res.robots_disallowed_root:
        print(f"error: {args.url} disallows all crawling in robots.txt - "
              "refusing to crawl", file=sys.stderr)
        return 2

    text = render(res)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text)
        dest = args.output
    else:
        print(text)
        dest = "stdout"

    stats = (f"{len(res.collections)} collections, {len(res.products)} products, "
             f"{len(res.pages)} pages, {len(res.articles)} articles, "
             f"{len(res.policies)} policies")
    print(f"wrote {dest}: {stats}; "
              f"{len(res.sitemaps_used)} sitemap(s) read, "
              f"{res.skipped_by_robots} URL(s) skipped per robots.txt",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
