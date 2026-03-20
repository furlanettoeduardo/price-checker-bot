"""
search/kabum.py
---------------
Scraper de busca para KaBuM (kabum.com.br).

Estratégia:
1. Extrai dados do __NEXT_DATA__ (Next.js) — mais estável.
2. Fallback: parseia cards de produto do HTML renderizado via Playwright.

Retorna lista de dicts com: name, price, store, url, source
"""

import json
import logging
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.kabum.com.br/busca/{query}"


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[dict]:
    """
    Busca produtos na KaBuM e retorna lista de ofertas.

    Parâmetros
    ----------
    query       : Texto de busca
    max_results : Número máximo de resultados
    min_price   : Filtro de preço mínimo (opcional)
    max_price   : Filtro de preço máximo (opcional)
    """
    slug = query.strip().replace(" ", "%20")
    url = _SEARCH_URL.format(query=slug)

    soup = fetch_page(url, use_playwright=True, use_cache=False, timeout=45)
    if soup is None:
        logger.warning("[KaBuM] Falha ao carregar página: %s", url)
        return []

    results = _parse_next_data(soup)
    if not results:
        results = _parse_html_cards(soup)

    if min_price is not None:
        results = [r for r in results if r["price"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["price"] <= max_price]

    logger.info("[KaBuM] %d resultado(s) para '%s'", len(results), query)
    return results[:max_results]


# ─────────────────────────────────────────────────────────────────────────────
# Estratégia 1: __NEXT_DATA__
# ─────────────────────────────────────────────────────────────────────────────

def _parse_next_data(soup: BeautifulSoup) -> list[dict]:
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except (json.JSONDecodeError, ValueError):
        return []

    products = _find_products(data)
    results = []
    for p in products:
        parsed = _parse_product(p)
        if parsed:
            results.append(parsed)

    if results:
        logger.debug("[KaBuM/__NEXT_DATA__] %d produtos extraídos", len(results))
    return results


def _find_products(obj, depth: int = 0) -> list:
    """Percorre o JSON recursivamente procurando lista de produtos KaBuM."""
    if depth > 12:
        return []
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            keys = set(obj[0].keys())
            if (keys & {"title", "name", "productName"}) and (keys & {"price", "salePrice", "priceFrom"}):
                return obj
        for v in obj:
            r = _find_products(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, dict):
        for v in obj.values():
            r = _find_products(v, depth + 1)
            if r:
                return r
    return []


def _parse_product(p: dict) -> Optional[dict]:
    try:
        title = p.get("title") or p.get("name") or p.get("productName") or ""
        if not title:
            return None

        price_raw = (
            p.get("price")
            or p.get("salePrice")
            or p.get("priceFrom")
            or p.get("specialPrice")
        )
        if price_raw is None:
            return None
        price = float(price_raw)
        if price <= 0:
            return None

        url = p.get("url") or p.get("link") or p.get("canonicalUrl") or ""
        if url and not url.startswith("http"):
            url = "https://www.kabum.com.br" + url

        return {
            "name": str(title)[:200],
            "price": price,
            "store": "KaBuM",
            "url": url,
            "source": "kabum",
        }
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Estratégia 2: parse HTML renderizado
# ─────────────────────────────────────────────────────────────────────────────

_ITEM_SELECTORS = [
    "article[data-testid='product-card']",
    "article.productCard",
    "[class*='productCard']",
    "[data-testid='product-card']",
    "[class*='product-card']",
]
_TITLE_SELECTORS = [
    "span.nameCard",
    "[data-testid='product-name']",
    "[class*='nameCard']",
    "h3",
    "h2",
]
_PRICE_SELECTORS = [
    "span.salePrice",
    "[data-testid='new-price']",
    "h4.finalPrice",
    "[class*='finalPrice']",
    "[class*='salePrice']",
    "span[class*='price']",
]
_LINK_SELECTORS = [
    "a[data-testid='product-link']",
    "a[href*='/produto/']",
    "a",
]


def _parse_html_cards(soup: BeautifulSoup) -> list[dict]:
    items: list = []
    for sel in _ITEM_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    if not items:
        logger.debug("[KaBuM/HTML] Nenhum card encontrado")
        return []

    results = []
    for card in items:
        try:
            title = ""
            for sel in _TITLE_SELECTORS:
                el = card.select_one(sel)
                if el:
                    title = el.get_text(strip=True)
                    break
            if not title:
                continue

            price_str = ""
            for sel in _PRICE_SELECTORS:
                el = card.select_one(sel)
                if el:
                    price_str = el.get_text(strip=True)
                    break
            if not price_str:
                continue
            price = normalize_price(price_str)
            if price is None or price <= 0:
                continue

            url = ""
            for sel in _LINK_SELECTORS:
                el = card.select_one(sel)
                if el and el.get("href"):
                    href = el["href"]
                    url = href if href.startswith("http") else "https://www.kabum.com.br" + href
                    break

            results.append({
                "name": title,
                "price": price,
                "store": "KaBuM",
                "url": url,
                "source": "kabum",
            })
        except Exception:
            continue

    logger.debug("[KaBuM/HTML] %d cards parseados", len(results))
    return results
