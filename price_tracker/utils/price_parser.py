"""
price_parser.py
---------------
Funções de normalização e análise de textos de preço em formato brasileiro.

Exemplos de entrada aceitos por normalize_price():
    "R$ 3.899,90"  → 3899.90
    "R$2.099,90"   → 2099.90
    "1.234,56"     → 1234.56
    "389,90"       → 389.90
    "R$ 1500"      → 1500.0
"""

import logging
import re
from typing import Optional

from bs4 import Tag

logger = logging.getLogger(__name__)


def normalize_price(raw: str) -> Optional[float]:
    """
    Converte uma string de preço no formato brasileiro para float.

    Retorna None se a conversão falhar ou o valor estiver fora de um
    intervalo razoável para hardware (R$ 1 – R$ 100.000).
    """
    if not raw:
        return None

    # Normaliza espaços e caracteres especiais
    cleaned = (
        raw.strip()
        .replace("\xa0", " ")   # espaço não-separável
        .replace("\n", "")
        .replace("\t", "")
    )

    # Extrai o primeiro grupo numérico válido (dígitos, ponto, vírgula)
    match = re.search(r"[\d.,]+", cleaned)
    if not match:
        return None

    number_str = match.group()

    if "," in number_str and "." in number_str:
        # Formato BR: 1.234,56 → milhar=ponto, decimal=vírgula
        number_str = number_str.replace(".", "").replace(",", ".")
    elif "," in number_str:
        # Só vírgula → separador decimal
        number_str = number_str.replace(",", ".")
    # Caso contrário, já está no formato float internacional (ex: "3899.90")

    try:
        value = float(number_str)
        if not (1.0 <= value <= 100_000.0):
            logger.warning(
                f"Preço fora do intervalo esperado: {value} (texto: '{raw}')"
            )
        return value
    except ValueError:
        logger.warning(f"Não foi possível converter '{number_str}' (original: '{raw}')")
        return None


def is_installment_text(text: str) -> bool:
    """
    Retorna True se o texto descreve um parcelamento (ex: "12x de R$ 389,90").
    Usado para filtrar preços parcelados na extração heurística.

    Padrões detectados:
        "10x de R$ 389,90"
        "12X R$208,32"
        "6x R$ 649,90"
    """
    return bool(re.search(r"\d+\s*[xX]\s*(de\s*)?R?\$", text))


def is_old_price(element: Tag) -> bool:
    """
    Retorna True se o elemento HTML parece representar um preço antigo
    ("de R$ X por R$ Y"), detectado por classes CSS comuns.
    """
    STALE_CLASSES = {
        "de", "old", "antes", "was", "original", "strike",
        "line-through", "preco-antigo", "oldprice", "price-old",
        "preco-de", "priceold", "price-before", "precoAntigo",
    }
    raw_classes = " ".join(element.get("class", [])).lower()
    element_classes = set(raw_classes.split())
    return bool(element_classes & STALE_CLASSES)
