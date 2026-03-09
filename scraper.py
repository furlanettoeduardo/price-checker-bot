"""
scraper.py
----------
Módulo de compatibilidade com versões anteriores.

A lógica de extração foi refatorada para o pacote price_tracker/:
  - price_tracker/core/price_extractor.py  <- get_product_price() (recomendado)
  - price_tracker/core/jsonld_parser.py    <- camada 1: JSON-LD
  - price_tracker/scrapers/               <- camada 2: scrapers por loja
  - price_tracker/core/heuristics.py      <- camada 3: fallback heuristico

Este arquivo mantém a função extract_price() para compatibilidade com
código antigo. Em código novo, use diretamente get_product_price().
"""

import logging
from typing import Optional

from price_tracker.core.price_extractor import get_product_price
from price_tracker.utils.price_parser import normalize_price  # noqa: F401

logger = logging.getLogger(__name__)


def extract_price(url: str, selectors: list) -> Optional[float]:
    """
    Wrapper de compatibilidade com a versão anterior do bot.

    Internamente delega para get_product_price() com estratégia em camadas:
      1. JSON-LD -> 2. Scraper de loja -> 3. Seletores CSS -> 4. Heurística

    Em código novo, prefira chamar get_product_price() diretamente para
    ter acesso ao método usado e ao score de confiança.
    """
    logger.debug("scraper.extract_price() -> delegando para get_product_price()")
    result = get_product_price(url, css_selectors=selectors)
    return result.get("price")
