"""
scrapers/kabum.py
-----------------
Scraper específico para kabum.com.br.

Kabum usa uma SPA React com classes geradas dinamicamente.
Os seletores abaixo foram validados e listados do mais ao menos estável.
Se um seletor quebrar, basta ajustá-lo aqui — sem tocar no restante do código.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)

# Seletores em ordem de prioridade (mais estável → menos estável)
_SELECTORS = [
    "h4.finalPrice",               # Histórico mais estável
    "[class*='finalPrice']",       # Variante por substring de classe
    "[data-testid='new-price']",   # Atributo de teste — relativamente estável
    ".sc-fzoLsD.dHatnu",           # Classe interna (pode mudar com deploy)
    ".priceCard",
    "[class*='priceCard']",
    ".regularPrice",
    "[itemprop='price']",          # Microdata — alternativa ao JSON-LD
]


def extract(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extrai o preço à vista de uma página de produto da Kabum.

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

            # Tenta primeiro o atributo 'content' (microdata)
            raw = el.get("content") or el.get_text(separator=" ", strip=True)
            price = normalize_price(raw)

            if price is not None:
                logger.info(f"[Kabum] Preço R$ {price:.2f} — seletor: '{selector}'")
                return {"price": price, "currency": "BRL", "confidence": 0.90}

        except Exception as exc:
            logger.debug(f"[Kabum] Erro no seletor '{selector}': {exc}")

    logger.warning("[Kabum] Nenhum seletor retornou preço válido.")
    return None
