"""
mercadolivre.py
---------------
Busca produtos via API pública do Mercado Livre (MLB — Brasil).
Não requer autenticação para buscas simples.

Documentação da API:
  https://developers.mercadolivre.com.br/pt_br/itens-e-buscas

Retorna lista de dicts com: name, price, store, url, source
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_API_URL = "https://api.mercadolibre.com/sites/MLB/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def search(
    query: str,
    max_results: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> list[dict]:
    """
    Busca produtos no Mercado Livre e retorna lista de ofertas.

    Parâmetros
    ----------
    query       : Texto de busca (nome do produto + palavras-chave)
    max_results : Número máximo de resultados (máximo suportado pela API: 50)
    min_price   : Filtro de preço mínimo (opcional)
    max_price   : Filtro de preço máximo (opcional)

    Retorna lista de dicts com: name, price, store, url, source
    """
    params: dict = {
        "q": query,
        "limit": min(max_results, 50),
        "sort": "price_asc",
    }
    if min_price is not None:
        params["price_min"] = min_price
    if max_price is not None:
        params["price_max"] = max_price

    try:
        resp = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        logger.warning(f"[MercadoLivre] Timeout ao buscar '{query}'")
        return []
    except requests.exceptions.RequestException as exc:
        logger.warning(f"[MercadoLivre] Erro na requisição para '{query}': {exc}")
        return []
    except ValueError:
        logger.warning(f"[MercadoLivre] Resposta não é JSON para '{query}'")
        return []

    results = []
    for item in data.get("results", []):
        try:
            price = float(item["price"])
            seller = item.get("seller", {}).get("nickname", "") or "MercadoLivre"
            # Limita o nome do vendedor para não poluir a planilha
            store = f"ML/{seller[:30]}"
            results.append({
                "name": item["title"],
                "price": price,
                "store": store,
                "url": item["permalink"],
                "source": "mercadolivre",
            })
        except (KeyError, ValueError, TypeError):
            continue

    logger.info(f"[MercadoLivre] {len(results)} resultado(s) para '{query}'")
    return results[:max_results]
