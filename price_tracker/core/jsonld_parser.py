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
    Extrai preço e campos adicionais de um objeto 'offers' de schema.org.

    Campos extraídos (quando disponíveis):
      - price             : preço promocional (price > lowPrice)
      - preco_sem_promocao: preço sem desconto (highPrice quando price != highPrice)
      - preco_pix         : preço à vista/Pix (via priceSpecification)
      - preco_parcelado   : valor de cada parcela (via priceSpecification)
      - parcelas          : número de parcelas (via priceSpecification)
    """
    result: dict = {
        "preco_sem_promocao": None,
        "preco_parcelado": None,
        "parcelas": None,
        "preco_pix": None,
    }

    # ── Extrai preço promocional principal ────────────────────────────────
    price = None
    for field in ("price", "lowPrice"):
        raw = offers.get(field)
        if raw is None:
            continue
        price = normalize_price(str(raw))
        if price is not None:
            currency = offers.get("priceCurrency", "BRL")
            logger.info(f"[JSON-LD] Preço via campo '{field}': {price} {currency}")
            result["price"] = price
            result["currency"] = currency
            result["confidence"] = 0.98
            result["method"] = "jsonld"
            break

    if price is None:
        return None

    # ── highPrice como preço sem promoção (quando diferente do price) ─────
    raw_high = offers.get("highPrice")
    if raw_high is not None:
        high = normalize_price(str(raw_high))
        if high is not None and high > price:
            result["preco_sem_promocao"] = high
            logger.info(f"[JSON-LD] Preço sem promoção (highPrice): {high}")

    # ── priceSpecification para parcelas e PIX ────────────────────────────
    spec = offers.get("priceSpecification")
    if isinstance(spec, list):
        for item in spec:
            _parse_price_specification(item, price, result)
    elif isinstance(spec, dict):
        _parse_price_specification(spec, price, result)

    return result


def _parse_price_specification(spec: dict, base_price: float, result: dict) -> None:
    """
    Analisa um único objeto priceSpecification e preenche result com
    preco_pix, parcelas e preco_parcelado quando identificados.
    """
    if not isinstance(spec, dict):
        return

    spec_type = str(spec.get("@type", "")).lower()
    name = str(spec.get("name", "")).lower()
    raw_val = spec.get("price")
    if raw_val is None:
        return
    val = normalize_price(str(raw_val))
    if val is None:
        return

    # PIX / à vista: valor menor que o preço base ou nome contém "pix"/"vista"
    if "pix" in name or "vista" in name or (val < base_price and result["preco_pix"] is None):
        result["preco_pix"] = val
        logger.info(f"[JSON-LD] Preço Pix/à vista via priceSpecification: {val}")
        return

    # Parcelamento: spec com numberOfPayments ou nome contendo parcela/installment
    n_payments = spec.get("numberOfPayments") or spec.get("numberOfInstallments")
    if n_payments:
        try:
            result["parcelas"] = int(n_payments)
            result["preco_parcelado"] = val
            logger.info(f"[JSON-LD] Parcelamento: {n_payments}x de {val}")
        except (ValueError, TypeError):
            pass
