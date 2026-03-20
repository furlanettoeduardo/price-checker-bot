"""
aggregator.py
-------------
Agrega resultados de múltiplas fontes de busca e retorna lista unificada
de ofertas ordenada por preço crescente.

As fontes são consultadas em PARALELO via ThreadPoolExecutor — o tempo
total é determinado pela fonte mais lenta, não pela soma de todas.

Fontes disponíveis: mercadolivre, zoom, kabum, pichau, terabyte, amazon

Uso programático:
    from price_tracker.search.aggregator import search

    result = search("RTX 4070", max_results=10, sources=["mercadolivre", "zoom"])
    # result = {
    #   "query": "RTX 4070",
    #   "offers": [{"name": ..., "price": ..., "store": ..., "url": ..., "source": ...}, ...],
    #   "min_price": 3299.90,
    #   "max_price": 3799.00,
    #   "total": 18,
    #   "timings": {"mercadolivre": 4.2, "zoom": 3.8},   # segundos por fonte
    # }

    # Passando tokens de API opcionais:
    result = search("RTX 4070", source_kwargs={"mercadolivre": {"access_token": "APP_USR-..."}})
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from price_tracker.search import amazon, kabum, mercadolivre, pichau, terabyte, zoom

logger = logging.getLogger(__name__)

# Registry of available search sources.
# Stored as module references (not function references) so that mock.patch
# can replace .search at test time without being bypassed by early binding.
_SOURCES: dict = {
    "mercadolivre": mercadolivre,
    "zoom": zoom,
    "kabum": kabum,
    "pichau": pichau,
    "terabyte": terabyte,
    "amazon": amazon,
}

DEFAULT_SOURCES: list[str] = ["mercadolivre", "zoom", "kabum", "pichau", "terabyte", "amazon"]

# Número máximo de fontes rodando em paralelo.
# Playwright lança um processo Chromium por thread — manter ≤ 6 evita pressão
# excessiva de memória em máquinas com RAM limitada.
_MAX_WORKERS = 6


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sources: Optional[list[str]] = None,
    source_kwargs: Optional[dict] = None,
    on_source_done: Optional[Callable[[str, int, float], None]] = None,
) -> dict:
    """
    Busca um produto em múltiplas fontes em PARALELO e retorna ofertas agregadas.

    Parâmetros
    ----------
    query         : Texto de busca (ex: "RTX 4070")
    max_results   : Máximo de resultados por fonte (padrão: 10)
    min_price     : Filtro de preço mínimo em R$ (opcional)
    max_price     : Filtro de preço máximo em R$ (opcional)
    sources       : Lista de fontes a consultar — usa DEFAULT_SOURCES se None
    source_kwargs : Kwargs extras por fonte, ex: {"mercadolivre": {"access_token": "..."}}
    on_source_done: Callback opcional chamado quando cada fonte termina:
                    on_source_done(source_name, n_results, elapsed_seconds)
                    Útil para exibir progresso em tempo real no CLI.

    Retorna
    -------
    {
        "query":     str,
        "offers":    list[dict],   # ordenado por preço crescente
        "min_price": float | None,
        "max_price": float | None,
        "total":     int,
        "timings":   dict[str, float],  # tempo em segundos por fonte
    }

    Cada oferta em "offers":
        {"name": str, "price": float, "store": str, "url": str, "source": str}
    """
    if sources is None:
        sources = DEFAULT_SOURCES
    if source_kwargs is None:
        source_kwargs = {}

    # Filtra fontes desconhecidas antes de disparar threads
    valid_sources: list[str] = []
    for name in sources:
        if name in _SOURCES:
            valid_sources.append(name)
        else:
            logger.warning(
                "[Aggregator] Fonte desconhecida: '%s' — ignorada. "
                "Fontes disponíveis: %s",
                name,
                ", ".join(_SOURCES),
            )

    all_offers: list[dict] = []
    timings: dict[str, float] = {}

    def _run_source(source_name: str) -> tuple[str, list[dict], float]:
        """Executa uma fonte e retorna (nome, resultados, tempo_decorrido)."""
        fn = _SOURCES[source_name]
        extra = source_kwargs.get(source_name, {})
        t0 = time.monotonic()
        try:
            results = fn.search(
                query,
                max_results=max_results,
                min_price=min_price,
                max_price=max_price,
                **extra,
            )
        except Exception as exc:
            logger.warning("[Aggregator] Erro ao consultar '%s': %s", source_name, exc)
            results = []
        elapsed = time.monotonic() - t0
        return source_name, results, elapsed

    n_workers = min(_MAX_WORKERS, len(valid_sources))
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_run_source, name): name for name in valid_sources}

        for future in as_completed(futures):
            source_name, results, elapsed = future.result()
            timings[source_name] = round(elapsed, 2)
            all_offers.extend(results)
            logger.info(
                "[Aggregator] %s: %d oferta(s) em %.1fs",
                source_name, len(results), elapsed,
            )
            if on_source_done is not None:
                try:
                    on_source_done(source_name, len(results), elapsed)
                except Exception:
                    pass

    all_offers.sort(key=lambda o: o["price"])

    prices = [o["price"] for o in all_offers]
    return {
        "query": query,
        "offers": all_offers,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "total": len(all_offers),
        "timings": timings,
    }
