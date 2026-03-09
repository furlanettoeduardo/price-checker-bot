"""
scrapers/terabyte.py
--------------------
Scraper específico para terabyteshop.com.br.

A Terabyte Shop usa estrutura HTML mais tradicional com IDs e classes
semânticas, o que torna os seletores relativamente estáveis.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SELECTORS = [
    "#prod-new-price",             # ID do preço principal — mais estável
    ".prod-new-price span",        # Span dentro do container de preço
    ".val_principal",              # Classe de valor principal
    "#price-view-default",
    "[class*='new-price']",
    "[itemprop='price']",          # Microdata
    ".preco-original",
    "span[id*='price']",
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai o preço à vista de uma página de produto da Terabyte Shop.

    Retorna
    -------
    {"price": float, "currency": "BRL", "confidence": float}
    ou None se nenhum seletor retornar preço válido.
    """
    for selector in _SELECTORS:
        try:
            el = soup.select_one(selector)
            if el is None:
                continue

            # Prioriza atributo 'content' (microdata schema.org)
            raw = el.get("content") or el.get_text(separator=" ", strip=True)
            price = normalize_price(raw)

            if price is not None:
                logger.info(f"[Terabyte] Preço R$ {price:.2f} — seletor: '{selector}'")
                return {"price": price, "currency": "BRL", "confidence": 0.90}

        except Exception as exc:
            logger.debug(f"[Terabyte] Erro no seletor '{selector}': {exc}")

    logger.warning("[Terabyte] Nenhum seletor retornou preço válido.")
    return None
