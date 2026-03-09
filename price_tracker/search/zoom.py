"""
zoom.py
-------
Scraper para Zoom.com.br — agregador de preços brasileiro.
Exige Playwright pois o site é renderizado com JavaScript (Next.js).

Estratégia:
1. Tenta extrair os dados do __NEXT_DATA__ (JSON embutido pelo Next.js) — muito
   mais confiável e estável do que parsear o HTML renderizado.
2. Fallback: parseia os cards de produto do HTML com seletores flexíveis.

Retorna lista de dicts com: name, price, store, url, source
"""

import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import parse_price

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.zoom.com.br/search?q={query}&sort=price"


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[dict]:
    """
    Busca produtos no Zoom.com.br e retorna lista de ofertas.

    Parâmetros
    ----------
    query       : Texto de busca
    max_results : Número máximo de resultados
    min_price   : Filtro de preço mínimo (opcional)
    max_price   : Filtro de preço máximo (opcional)
    """
    url = _SEARCH_URL.format(query=query.replace(" ", "+"))
    # Zoom requer Playwright (React/Next.js)
    soup = fetch_page(url, use_playwright=True, use_cache=False, timeout=45)

    if soup is None:
        logger.warning(f"[Zoom] Falha ao carregar página: {url}")
        return []

    # Tenta __NEXT_DATA__ primeiro (mais estável)
    results = _parse_next_data(soup, query)
    if not results:
        # Fallback: parse HTML renderizado
        results = _parse_html_cards(soup, query)

    # Aplica filtros de preço
    if min_price is not None:
        results = [r for r in results if r["price"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["price"] <= max_price]

    logger.info(f"[Zoom] {len(results)} resultado(s) para '{query}'")
    return results[:max_results]


# ─────────────────────────────────────────────────────────────────────────────
# Estratégia 1: extrair dados do __NEXT_DATA__
# ─────────────────────────────────────────────────────────────────────────────

def _parse_next_data(soup: BeautifulSoup, query: str) -> list[dict]:
    """Extrai ofertas do JSON __NEXT_DATA__ embutido pelo Next.js."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []

    try:
        data = json.loads(tag.string)
    except (json.JSONDecodeError, ValueError):
        return []

    # Navega pela estrutura do Next.js até encontrar os produtos
    # A estrutura exata pode variar; procuramos recursivamente por listas de offers
    offers = _find_offers_in_json(data)
    results = []
    for offer in offers:
        try:
            result = _parse_offer_dict(offer)
            if result:
                results.append(result)
        except Exception:
            continue

    if results:
        logger.debug(f"[Zoom/__NEXT_DATA__] {len(results)} ofertas extraídas")
    return results


def _find_offers_in_json(obj, depth: int = 0) -> list:
    """
    Percorre recursivamente o JSON Next.js procurando por listas de ofertas.
    Heurística: lista com dicts que têm 'price' ou 'name' ou 'store'.
    """
    if depth > 8:
        return []
    if isinstance(obj, list):
        if len(obj) > 0 and isinstance(obj[0], dict):
            keys = set(obj[0].keys())
            if keys & {"price", "name", "store", "seller", "title", "storeName"}:
                return obj
        for item in obj:
            found = _find_offers_in_json(item, depth + 1)
            if found:
                return found
    elif isinstance(obj, dict):
        for val in obj.values():
            found = _find_offers_in_json(val, depth + 1)
            if found:
                return found
    return []


def _parse_offer_dict(offer: dict) -> Optional[dict]:
    """Tenta extrair name, price, store, url de um dict de oferta do Zoom."""
    # Preço
    price_raw = (
        offer.get("bestPrice") or offer.get("price") or
        offer.get("salePrice") or offer.get("installment", {}).get("totalAmount")
    )
    if price_raw is None:
        return None
    price = _to_float(price_raw)
    if not price:
        return None

    # Nome
    name = (
        offer.get("name") or offer.get("title") or
        offer.get("productName") or offer.get("description", "")
    )
    if not name:
        return None

    # Loja
    store_raw = (
        offer.get("storeName") or offer.get("store") or
        offer.get("seller") or offer.get("sellerName") or "Zoom"
    )
    store = store_raw if isinstance(store_raw, str) else (
        store_raw.get("name") or store_raw.get("storeName") or "Zoom"
        if isinstance(store_raw, dict) else "Zoom"
    )

    # URL
    url = (
        offer.get("url") or offer.get("link") or
        offer.get("href") or offer.get("storeUrl") or ""
    )
    if url and not url.startswith("http"):
        url = "https://www.zoom.com.br" + url

    return {
        "name": str(name)[:200],
        "price": price,
        "store": str(store)[:60],
        "url": url,
        "source": "zoom",
    }


def _to_float(val) -> Optional[float]:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        return parse_price(val)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Estratégia 2: parse do HTML renderizado
# ─────────────────────────────────────────────────────────────────────────────

_PRICE_RE = re.compile(r"R\$[\s\xa0]*[\d.,]+")


def _parse_html_cards(soup: BeautifulSoup, query: str) -> list[dict]:
    """
    Fallback: parseia cards de produto do HTML renderizado.
    Usa seletores flexíveis porque o Zoom pode mudar as classes entre deploys.
    """
    # Candidatos a container de offer: article, li, div com classes características
    candidates = (
        soup.find_all("article")
        or soup.select("[class*='offer']")
        or soup.select("[class*='product-card']")
        or soup.select("[class*='ProductCard']")
        or soup.select("[data-testid]")
    )

    results = []
    for card in candidates:
        result = _extract_card(card)
        if result:
            results.append(result)

    if results:
        logger.debug(f"[Zoom/HTML] {len(results)} cards parseados")
    return results


def _extract_card(card) -> Optional[dict]:
    """Extrai dados de um card de produto do HTML do Zoom."""
    # ── Preço ──────────────────────────────────────────────────────────────
    price_tag = (
        card.find(attrs={"data-testid": re.compile(r"price|preco", re.I)})
        or card.find(class_=re.compile(r"price|preco|valor|best", re.I))
    )
    # Fallback: procura qualquer texto com R$
    if price_tag is None:
        for tag in card.find_all(string=_PRICE_RE):
            price_tag = tag.parent
            break

    if price_tag is None:
        return None

    price = parse_price(price_tag.get_text(strip=True))
    if price is None:
        return None

    # ── Nome ───────────────────────────────────────────────────────────────
    name_tag = (
        card.find(attrs={"data-testid": re.compile(r"name|title|product", re.I)})
        or card.find("h2") or card.find("h3")
        or card.find("a", title=True)
    )
    if name_tag is None:
        return None
    name = name_tag.get("title") or name_tag.get_text(strip=True)
    if not name:
        return None

    # ── Loja ───────────────────────────────────────────────────────────────
    store_tag = (
        card.find(attrs={"data-testid": re.compile(r"store|seller|loja", re.I)})
        or card.find(class_=re.compile(r"store|seller|loja|merchant|retailer", re.I))
    )
    store = store_tag.get_text(strip=True) if store_tag else "Zoom"

    # ── URL ────────────────────────────────────────────────────────────────
    link = card.find("a", href=True)
    url = link["href"] if link else ""
    if url and url.startswith("/"):
        url = "https://www.zoom.com.br" + url

    return {
        "name": name[:200],
        "price": price,
        "store": store[:60] or "Zoom",
        "url": url,
        "source": "zoom",
    }
