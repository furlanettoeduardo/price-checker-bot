"""
search/terabyte.py
------------------
Scraper de busca para Terabyte Shop (terabyteshop.com.br).

Estratégia:
1. Tenta buscar sem Playwright (HTML tradicional) — mais rápido.
2. Fallback com Playwright se não encontrar itens.
3. Parseia cards com seletores estáveis do Terabyte.

Retorna lista de dicts com: name, price, store, url, source
"""

import logging
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.terabyteshop.com.br/busca?ns_query={query}"

_ITEM_SELECTORS = [
    ".product-item",
    ".pbox",
    "[class*='product-item']",
    "li.list-product",
]


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[dict]:
    """
    Busca produtos na Terabyte Shop e retorna lista de ofertas.

    Parâmetros
    ----------
    query       : Texto de busca
    max_results : Número máximo de resultados
    min_price   : Filtro de preço mínimo (opcional)
    max_price   : Filtro de preço máximo (opcional)
    """
    url = _SEARCH_URL.format(query=quote_plus(query.strip()))

    # Terabyte tem HTML tradicional; tenta sem Playwright primeiro
    soup = fetch_page(url, use_playwright=False, use_cache=False, timeout=20)
    if soup is None or not _has_items(soup):
        soup = fetch_page(url, use_playwright=True, use_cache=False, timeout=45)

    if soup is None:
        logger.warning("[Terabyte] Falha ao carregar página: %s", url)
        return []

    results = _parse_html_cards(soup)
    results = _relevance_filter(results, query)

    if min_price is not None:
        results = [r for r in results if r["price"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["price"] <= max_price]

    logger.info("[Terabyte] %d resultado(s) para '%s'", len(results), query)
    return results[:max_results]


def _relevance_filter(results: list[dict], query: str) -> list[dict]:
    """
    Remove resultados cuja categoria não está relacionada à busca.
    A Terabyte exibe produtos em destaque (bestsellers, promoções) misturados
    com os resultados reais; este filtro elimina os irrelevantes.
    """
    words = [w.lower() for w in query.split() if len(w) > 2]
    if not words:
        return results
    return [r for r in results if any(w in r["name"].lower() for w in words)]


def _has_items(soup: BeautifulSoup) -> bool:
    for sel in _ITEM_SELECTORS:
        if soup.select(sel):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Parse HTML
# ─────────────────────────────────────────────────────────────────────────────

_TITLE_SELECTORS = [
    "a.product-item__name h2",
    "a.product-item__name",
    "[class*='product-item__name']",
    "h3 a",
    ".prod-name a",
    ".prod-name",
    "h3",
    "h2",
]
_PRICE_SELECTORS = [
    ".product-item__new-price span",  # <span> direto com valor (ex: R$ 4.799,90)
    ".product-item__new-price",
    "#prod-new-price span",
    ".prod-new-price span",
    ".prod-new-price",
    "[class*='new-price'] span",
    "[class*='new-price']",
]
_LINK_SELECTORS = [
    "a.product-item__name",
    "a[href*='/produto/']",
    "h3 a",
    ".prod-name a",
    "a[href]",
]


def _parse_html_cards(soup: BeautifulSoup) -> list[dict]:
    items: list = []
    for sel in _ITEM_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    if not items:
        logger.debug("[Terabyte/HTML] Nenhum card encontrado")
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
                    url = href if href.startswith("http") else "https://www.terabyteshop.com.br" + href
                    break

            results.append({
                "name": title,
                "price": price,
                "store": "Terabyte",
                "url": url,
                "source": "terabyte",
            })
        except Exception:
            continue

    logger.debug("[Terabyte/HTML] %d cards parseados", len(results))
    return results
