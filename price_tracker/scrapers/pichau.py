"""
scrapers/pichau.py
------------------
Scraper específico para pichau.com.br.

Pichau usa Material UI (MUI). As classes `.MuiTypography-*` são geradas
pelo framework e tendem a ser estáveis, mas o texto "R$" às vezes fica
separado do número em spans distintos — por isso verificamos o elemento
pai quando necessário.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

_SELECTORS = [
    # Preço em texto completo dentro de H1 (layout desktop)
    "h1.MuiTypography-h1",
    ".MuiTypography-h1",
    # Containers de preço com classes semânticas
    "[class*='ProductPrice']",
    "[class*='productPrice']",
    ".productPrice",
    # Seletores genéricos de preço MUI
    "[class*='price'] .MuiTypography-root",
    "span[class*='price']",
    # Microdata
    "[itemprop='price']",
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai o preço à vista de uma página de produto da Pichau.

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

            raw = el.get("content") or el.get_text(separator=" ", strip=True)
            price = normalize_price(raw)

            if price is not None:
                logger.info(f"[Pichau] Preço R$ {price:.2f} — seletor: '{selector}'")
                return {"price": price, "currency": "BRL", "confidence": 0.88}

        except Exception as exc:
            logger.debug(f"[Pichau] Erro no seletor '{selector}': {exc}")

    logger.warning("[Pichau] Nenhum seletor retornou preço válido.")
    return None
