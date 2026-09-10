# llms-txt-gen

Generate a clean, well-formed `llms.txt` for any ecommerce store.

`llms.txt` is the emerging convention for telling LLM agents what a site
offers and where things live (like `robots.txt`, but for orientation instead
of permission). Almost no store has one yet, and writing one by hand means
digging through sitemaps and policy pages. This tool does that crawl for you
and emits a file that follows the [llmstxt.org](https://llmstxt.org) format.

Companion to [agent-ready](https://github.com/DeepanshuPal/agent-ready),
which audits stores for agent-readiness - `llms.txt` was the most common
cheap gap it found, so this closes it.

## What it does

1. Reads `robots.txt` first and respects it: disallowed paths are never
   fetched (and a store that disallows all crawling gets a refusal, not a
   crawl). Sitemaps declared in robots.txt are used when present.
2. Discovers pages through XML sitemaps - never brute-force link walking -
   and buckets them into collections / products / pages / articles / policies
   by URL shape. Shopify sub-sitemaps are understood natively; other platforms
   fall back to generic path patterns.
3. Fetches a capped, rate-limited sample (default 0.4s between requests) and
   annotates each link with its real `<title>` and meta description, cleaned
   of store-name boilerplate and SEO cruft. Soft-404s (200 status, "Page Not
   Found" template - common in stale Shopify sitemaps) are detected and dropped.
4. Probes `/products.json`; if the store exposes its catalog as JSON, that
   gets its own "Machine-readable endpoints" section - the single most useful
   thing in the file for a shopping agent.
5. Emits `llms.txt` in the standard format: `# Store`, `> one-line
   description`, then `##` link sections.

## Install and run

```bash
git clone https://github.com/DeepanshuPal/llms-txt-gen.git
cd llms-txt-gen
pip install -r requirements.txt

python3 llms_txt_gen.py https://www.tentree.com -o llms.txt
```

Requires Python 3.9+ and `requests`. Useful flags: `--max-products N`,
`--max-collections N`, `--delay SECONDS`, `--timeout SECONDS`.

Deploy the result by uploading `llms.txt` to the store's web root.

## Sample output

Generated against `tentree.com` (full files in [`examples/`](examples/)):

```
# Tentree

> Sustainable Apparel & Accessories for Women & Men. Made with Hemp, Organic Cotton, Recycled Polyester & Tencel. Every Item Plants 10 Trees. 120+ Million Planted.

## Collections

- [Sustainable Men's Hoodies, Sweatshirts & Fleece Hoodies](https://www.tentree.com/collections/mens-hoodies): Canada's Most Sustainable Men's hoodies, sweatshirts, graphic hoodies, crew neck sweaters and fleece hoodies. Eco Friendly fabric made…
- [Men's Joggers & Sweatpants - Organic Cotton](https://www.tentree.com/collections/men-pants): The Most Eco-Friendly Pants on Earth. Comfy, Durable + Ethically Crafted with Recycled Plastics, Hemp & Organic Cotton. 10 Trees Planted…

## Policies

- [Refund policy](https://www.tentree.com/policies/refund-policy)
- [Privacy policy](https://www.tentree.com/policies/privacy-policy)
...

## Machine-readable endpoints

- [Product catalog (JSON)](https://www.tentree.com/products.json): full catalog with variants, prices and availability; paginate with ?page=N&limit=250
```

## What testing against real stores surfaced

- **tentree.com** - clean run: 20 collections, 10 products, 14 pages,
  5 articles, 4 policies, live `products.json`.
- **allbirds.com** - their `robots.txt` disallows `/policies/` (the Shopify
  default), so the policy section is correctly omitted; and every collection
  URL in their sitemap is a stale soft-404, so those got dropped too. The
  generated file is thinner - but honestly so.
- **gymshark.com** - full link sections, but no machine-readable section:
  their `products.json` 403s scripted clients, so there's no endpoint to
  point agents at.

## Roadmap

- `--full-catalog` mode: embed every product, not a sample
- price/availability inline via products.json enrichment
- WordPress/WooCommerce and Magento sitemap dialects
- diff mode: regenerate and show what changed since the last llms.txt

## License

MIT
