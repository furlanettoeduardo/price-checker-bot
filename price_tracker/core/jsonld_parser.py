"""
jsonld_parser.py
----------------
Camada 1 de extração — dados estruturados JSON-LD (schema.org/Product).

É o método mais estável porque:
  - Os dados são fornecidos intencionalmente pela loja para fins de SEO
  - Não dependem de classes CSS (que mudam com frequência)
  - São atualizados junto com o preço real da página

Suporta os formatos de JSON-LD mais comuns em e-commerces brasileiros:
  - Objeto Product direto
  - Lista de objetos
  - Grafo (@graph) com objetos aninhados
"""

import json
import logging
from typing import Optional

from bs4 import BeautifulSoup

from price_tracker.utils.price_parser import normalize_price

logger = logging.getLogger(__name__)


def extract_price_jsonld(soup: BeautifulSoup) -> Optional[dict]:
    """
    Analisa todos os blocos <script type="application/ld+json"> da página
    buscando um objeto do tipo Product com informação de oferta.

    Retorna
    -------
    {
        "price"     : float,
        "currency"  : str,     # geralmente "BRL"
        "confidence": float,   # 0.98 — dado estruturado é muito confiável
        "method"    : "jsonld"
    }
    ou None se não encontrar preço válido.
    """
    scripts = soup.find_all("script", type="application/ld+json")
    if not scripts:
        logger.debug("Página sem blocos JSON-LD.")
        return None

    for script in scripts:
        try:
            raw = script.string or ""
            if not raw.strip():
                continue
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.debug(f"Bloco JSON-LD inválido, ignorado: {exc}")
            continue

        # O valor pode ser um único objeto ou uma lista de objetos
        objects = data if isinstance(data, list) else [data]

        for obj in objects:
            result = _parse_object(obj)
            if result:
                return result

    logger.debug("JSON-LD presente mas sem Product/offers com preço válido.")
    return None


def _parse_object(obj: dict) -> Optional[dict]:
    """
    Analisa um único objeto JSON-LD.
    Suporta:
      - {"@type": "Product", "offers": {...}}
      - {"@graph": [{"@type": "Product", ...}]}
      - {"@type": ["Product", "Thing"], ...}
    """
    if not isinstance(obj, dict):
        return None

    # Suporte a @graph (vários objetos num mesmo bloco)
    if "@graph" in obj:
        for item in obj["@graph"]:
            result = _parse_object(item)
            if result:
                return result

    obj_type = obj.get("@type", "")
    types = [obj_type] if isinstance(obj_type, str) else list(obj_type)

    if not any("product" in t.lower() for t in types):
        return None

    offers = obj.get("offers", {})
    # offers pode ser um objeto único ou uma lista (AggregateOffer)
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    return _extract_from_offers(offers)


def _extract_from_offers(offers: dict) -> Optional[dict]:
    """
    Extrai preço de um objeto 'offers' de schema.org.
    Prioridade: price > lowPrice > highPrice
    """
    for field in ("price", "lowPrice", "highPrice"):
        raw = offers.get(field)
        if raw is None:
            continue

        price = normalize_price(str(raw))
        if price is not None:
            currency = offers.get("priceCurrency", "BRL")
            logger.info(
                f"[JSON-LD] Preço via campo '{field}': "
                f"{price} {currency}"
            )
            return {
                "price": price,
                "currency": currency,
                "confidence": 0.98,
                "method": "jsonld",
            }

    return None
