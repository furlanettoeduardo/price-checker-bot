"""
mercadolivre.py
---------------
Scraper para o Mercado Livre Brasil (lista.mercadolivre.com.br).

Estratégia:
1. Tenta extrair dados do __NEXT_DATA__ (JSON embutido pelo Next.js).
2. Fallback: parseia os cards de produto do HTML renderizado via Playwright.

Nota: a API pública do ML (/sites/MLB/search?q=...) requer permissões
elevadas não disponíveis para aplicativos comuns. O scraping da página de
resultados é a abordagem mais confiável para buscas por palavra-chave.

Retorna lista de dicts com: name, price, store, url, source
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://lista.mercadolivre.com.br/{query}"


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    # kept for API-compatibility with aggregator / search_cli kwargs
    access_token: Optional[str] = None,
    app_id: Optional[str] = None,
    secret_key: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> list[dict]:
    """
    Busca produtos no Mercado Livre e retorna lista de ofertas.

    Parâmetros
    ----------
    query       : Texto de busca
    max_results : Número máximo de resultados
    min_price   : Filtro de preço mínimo (opcional)
    max_price   : Filtro de preço máximo (opcional)
    """
    slug = query.strip().replace(" ", "-")
    url = _SEARCH_URL.format(query=quote_plus(slug, safe="-"))

    soup = fetch_page(url, use_playwright=True, use_cache=False, timeout=45)
    if soup is None:
        logger.warning("[MercadoLivre] Falha ao carregar página: %s", url)
        return []

    results = _parse_next_data(soup)
    if not results:
        results = _parse_html_cards(soup)

    if min_price is not None:
        results = [r for r in results if r["price"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["price"] <= max_price]

    logger.info("[MercadoLivre] %d resultado(s) para '%s'", len(results), query)
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

    items = _collect_items_from_json(data)
    results = []
    for item in items:
        parsed = _parse_item_dict(item)
        if parsed:
            results.append(parsed)

    if results:
        logger.debug("[MercadoLivre/__NEXT_DATA__] %d itens extraídos", len(results))
    return results


def _collect_items_from_json(obj, depth: int = 0) -> list:
    """Percorre recursivamente o JSON procurando listas de anúncios ML."""
    if depth > 12:
        return []
    if isinstance(obj, list):
        # Heurística: lista cujos elementos têm "title" e "price"
        if obj and isinstance(obj[0], dict) and "title" in obj[0] and "price" in obj[0]:
            return obj
        results = []
        for v in obj:
            results.extend(_collect_items_from_json(v, depth + 1))
        return results
    if isinstance(obj, dict):
        results = []
        for v in obj.values():
            results.extend(_collect_items_from_json(v, depth + 1))
        return results
    return []


def _parse_item_dict(item: dict) -> Optional[dict]:
    try:
        title = item.get("title") or item.get("name") or ""
        if not title:
            return None

        raw_price = (
            item.get("price")
            or item.get("sale_price")
            or (item.get("prices") or {}).get("price")
        )
        if raw_price is None:
            return None
        price = float(raw_price)
        if price <= 0:
            return None

        permalink = item.get("permalink") or item.get("url") or ""
        seller = (item.get("seller") or {}).get("nickname", "") or "MercadoLivre"

        return {
            "name": title,
            "price": price,
            "store": f"ML/{seller[:30]}",
            "url": permalink,
            "source": "mercadolivre",
        }
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Estratégia 2: parse HTML renderizado
# ─────────────────────────────────────────────────────────────────────────────

# Seletores CSS do Mercado Livre (atualizado para 2025)
_ITEM_SELECTORS = [
    "li.ui-search-layout__item",
    "div.ui-search-result__wrapper",
    "li.results-item",
]
_TITLE_SELECTORS = [
    "h2.poly-box",
    "h2.ui-search-item__title",
    "a.ui-search-item__brand-discoverability > h2",
    ".poly-component__title",
    ".ui-search-item__title",
]
_PRICE_SELECTORS = [
    "span.andes-money-amount__fraction",
    "span.price-tag-fraction",
    "span.poly-price__current .andes-money-amount__fraction",
]
_LINK_SELECTORS = [
    "a.poly-component__title",
    "a.ui-search-result__content-wrapper",
    "a.ui-search-link",
]
_SELLER_SELECTORS = [
    ".poly-component__seller",
    ".ui-search-official-store-label",
    ".ui-search-item__group__element--seller-info",
]


def _parse_html_cards(soup: BeautifulSoup) -> list[dict]:
    items: list = []
    for sel in _ITEM_SELECTORS:
        items = soup.select(sel)
        if items:
            break
    if not items:
        logger.debug("[MercadoLivre/HTML] Nenhum card encontrado")
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
                    price_str = el.get_text(strip=True).replace(".", "").replace(",", ".")
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
                    url = el["href"]
                    break

            seller = "MercadoLivre"
            for sel in _SELLER_SELECTORS:
                el = card.select_one(sel)
                if el:
                    seller = el.get_text(strip=True)[:30]
                    break

            results.append({
                "name": title,
                "price": price,
                "store": f"ML/{seller}",
                "url": url,
                "source": "mercadolivre",
            })
        except Exception:
            continue

    logger.debug("[MercadoLivre/HTML] %d cards parseados", len(results))
    return results
