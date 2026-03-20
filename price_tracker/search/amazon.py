"""
search/amazon.py
----------------
Scraper de busca para Amazon Brasil (amazon.com.br).

AVISO: A Amazon usa sistemas sofisticados de detecção de bots. Esta
implementação usa Playwright + modo stealth, mas pode receber CAPTCHA.
Quando CAPTCHA é detectado, retorna lista vazia com aviso no log.

Estratégia:
1. Playwright + stealth para carregar a página de resultados.
2. Parseia cards com seletores estáveis (data-asin, data-component-type).

Retorna lista de dicts com: name, price, store, url, source
"""

import logging
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from price_tracker.utils.html_fetcher import fetch_page
from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.amazon.com.br/s?k={query}"
_BASE_URL = "https://www.amazon.com.br"


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[dict]:
    """
    Busca produtos na Amazon Brasil e retorna lista de ofertas.

    Parâmetros
    ----------
    query       : Texto de busca
    max_results : Número máximo de resultados
    min_price   : Filtro de preço mínimo (opcional)
    max_price   : Filtro de preço máximo (opcional)
    """
    url = _SEARCH_URL.format(query=quote_plus(query.strip()))

    soup = fetch_page(url, use_playwright=True, use_cache=False, timeout=45)
    if soup is None:
        logger.warning("[Amazon] Falha ao carregar página: %s", url)
        return []

    if _is_captcha(soup):
        logger.warning("[Amazon] CAPTCHA detectado — resultados indisponíveis para '%s'.", query)
        return []

    results = _parse_html_cards(soup)

    if min_price is not None:
        results = [r for r in results if r["price"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["price"] <= max_price]

    logger.info("[Amazon] %d resultado(s) para '%s'", len(results), query)
    return results[:max_results]


def _is_captcha(soup: BeautifulSoup) -> bool:
    return bool(
        soup.select_one("form[action='/errors/validateCaptcha']")
        or soup.select_one("#captchacharacters")
        or soup.find(string=lambda t: t and "robot" in t.lower() and "unusual" in t.lower())
    )


# ─────────────────────────────────────────────────────────────────────────────
# Parse HTML
# ─────────────────────────────────────────────────────────────────────────────

def _parse_html_cards(soup: BeautifulSoup) -> list[dict]:
    # Seletor principal: cards com data-asin não-vazio
    items = [
        el for el in soup.select("[data-asin]")
        if el.get("data-asin")
    ]
    if not items:
        logger.debug("[Amazon/HTML] Nenhum card encontrado")
        return []

    results = []
    for card in items:
        try:
            # Título
            title_el = (
                card.select_one("h2 a span")
                or card.select_one("h2 span")
                or card.select_one("[data-cy='title-recipe-title']")
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # Preço — .a-offscreen contém texto acessível com valor completo
            price = None
            price_el = card.select_one(".a-price .a-offscreen")
            if price_el:
                price = normalize_price(price_el.get_text(strip=True))

            # Fallback: compõe whole + fraction
            if price is None:
                whole = card.select_one(".a-price-whole")
                frac = card.select_one(".a-price-fraction")
                if whole:
                    raw = whole.get_text(strip=True).rstrip(",.")
                    if frac:
                        raw += "," + frac.get_text(strip=True)
                    price = normalize_price(raw)

            if price is None or price <= 0:
                continue

            # URL
            link_el = card.select_one("h2 a")
            if link_el and link_el.get("href"):
                href = link_el["href"]
                url = href if href.startswith("http") else _BASE_URL + href
            else:
                asin = card.get("data-asin", "")
                url = f"{_BASE_URL}/dp/{asin}" if asin else ""

            results.append({
                "name": title,
                "price": price,
                "store": "Amazon BR",
                "url": url,
                "source": "amazon",
            })
        except Exception:
            continue

    logger.debug("[Amazon/HTML] %d cards parseados", len(results))
    return results
