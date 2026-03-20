"""
aggregator.py
-------------
Agrega resultados de múltiplas fontes de busca e retorna lista unificada
de ofertas ordenada por preço crescente.

Fontes disponíveis: mercadolivre, zoom

Uso programático:
    from price_tracker.search.aggregator import search

    result = search("RTX 4070", max_results=10, sources=["mercadolivre", "zoom"])
    # result = {
    #   "query": "RTX 4070",
    #   "offers": [{"name": ..., "price": ..., "store": ..., "url": ..., "source": ...}, ...],
    #   "min_price": 3299.90,
    #   "max_price": 3799.00,
    #   "total": 18,
    # }

    # Passando tokens de API opcionais:
    result = search("RTX 4070", source_kwargs={"mercadolivre": {"access_token": "APP_USR-..."}})
"""

import logging
from typing import Optional

from price_tracker.search import mercadolivre, zoom

logger = logging.getLogger(__name__)

# Registry of available search sources.
# Stored as module references (not function references) so that mock.patch
# can replace .search at test time without being bypassed by early binding.
_SOURCES: dict = {
    "mercadolivre": mercadolivre,
    "zoom": zoom,
}

DEFAULT_SOURCES: list[str] = ["mercadolivre", "zoom"]


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sources: Optional[list[str]] = None,
    source_kwargs: Optional[dict] = None,
) -> dict:
    """
    Busca um produto em múltiplas fontes e retorna ofertas agregadas.

    Parâmetros
    ----------
    query        : Texto de busca (ex: "RTX 4070")
    max_results  : Máximo de resultados por fonte (padrão: 10)
    min_price    : Filtro de preço mínimo em R$ (opcional)
    max_price    : Filtro de preço máximo em R$ (opcional)
    sources      : Lista de fontes a consultar — usa DEFAULT_SOURCES se None
    source_kwargs: Kwargs extras por fonte, ex: {"mercadolivre": {"access_token": "..."}}

    Retorna
    -------
    {
        "query":     str,
        "offers":    list[dict],   # ordenado por preço crescente
        "min_price": float | None,
        "max_price": float | None,
        "total":     int,
    }

    Cada oferta em "offers":
        {"name": str, "price": float, "store": str, "url": str, "source": str}
    """
    if sources is None:
        sources = DEFAULT_SOURCES
    if source_kwargs is None:
        source_kwargs = {}

    all_offers: list[dict] = []

    for source_name in sources:
        fn = _SOURCES.get(source_name)
        if fn is None:
            logger.warning(
                "[Aggregator] Fonte desconhecida: '%s' — ignorada. "
                "Fontes disponíveis: %s",
                source_name,
                ", ".join(_SOURCES),
            )
            continue

        extra = source_kwargs.get(source_name, {})
        try:
            results = fn.search(
                query,
                max_results=max_results,
                min_price=min_price,
                max_price=max_price,
                **extra,
            )
            logger.info("[Aggregator] %s: %d oferta(s)", source_name, len(results))
            all_offers.extend(results)
        except Exception as exc:
            logger.warning("[Aggregator] Erro ao consultar '%s': %s", source_name, exc)

    all_offers.sort(key=lambda o: o["price"])

    prices = [o["price"] for o in all_offers]
    return {
        "query": query,
        "offers": all_offers,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "total": len(all_offers),
    }
