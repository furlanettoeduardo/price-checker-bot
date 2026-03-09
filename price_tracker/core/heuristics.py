"""
heuristics.py
-------------
Camada 3 — extração heurística de preços (último recurso / fallback).

Estratégia:
  1. Busca todos os nós de texto da página com padrão de preço brasileiro
  2. Aplica filtros de exclusão:
       - Parcelamentos  ("12x de R$ 208,32")
       - Preços antigos (elemento com classe "old-price", "preco-de" etc.)
       - Seções irrelevantes (carrossel, rodapé, recomendações…)
  3. Pontua cada candidato por sinais de relevância (tag HTML, classe CSS…)
  4. Retorna o candidato com maior pontuação

Logging:
  - [WARNING] Heurística acionada (sempre que esse módulo é usado)
  - [DEBUG]   Candidatos filtrados e seus motivos
  - [INFO]    Melhor candidato selecionado com score
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from price_tracker.utils.price_parser import (
    is_installment_text,
    is_old_price,
    normalize_price,
)

logger = logging.getLogger(__name__)

# Padrão de preço brasileiro: "R$ 3.899,90" ou "3.899,90" ou "R$389,90"
_PRICE_RE = re.compile(
    r"R\$\s*\d[\d.]*,\d{2}|\d{1,3}(?:\.\d{3})+,\d{2}",
    re.IGNORECASE,
)

# Palavras-chave em id/class dos ancestrais que indicam seção a ignorar
_IGNORE_SECTIONS = {
    "related", "similar", "carousel", "recommendation", "suggest",
    "compare", "also", "previously", "viewed", "shelf", "banner",
    "footer", "header", "nav", "breadcrumb", "menu", "sidebar",
    "installment", "parcel", "parcela",
}

# Classes CSS que sugerem que o elemento é o preço principal
_PRICE_SIGNAL_CLASSES = {
    "price", "preco", "valor", "final", "sale",
    "current", "destaque", "principal", "buy",
}


def extract_price_heuristic(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extração heurística: busca e pontua candidatos de preço no HTML.

    Retorna
    -------
    {
        "price"     : float,
        "currency"  : "BRL",
        "confidence": float,   # 0.0 – 1.0
        "method"    : "heuristic"
    }
    ou None se nenhum candidato plausível for encontrado.
    """
    logger.warning("[Heurística] Iniciando extração heurística de preço.")

    candidates: list[dict] = []

    # Itera sobre todos os nós de texto que contêm padrão de preço
    for text_node in soup.find_all(string=_PRICE_RE):
        parent = text_node.parent
        if not isinstance(parent, Tag):
            continue

        text = text_node.strip()

        # ── Filtros de exclusão ──────────────────────────────────────────
        if is_installment_text(text):
            logger.debug(f"Heurística: ignorando parcelamento — '{text[:60]}'")
            continue

        if is_old_price(parent):
            logger.debug(f"Heurística: ignorando preço antigo — '{text[:60]}'")
            continue

        if _in_ignored_section(parent):
            logger.debug(f"Heurística: ignorando seção irrelevante — '{text[:60]}'")
            continue

        # ── Extração e pontuação ────────────────────────────────────────
        for match in _PRICE_RE.findall(text):
            price = normalize_price(match)
            if price is None:
                continue

            score = _score_candidate(price, parent, text)
            candidates.append({
                "price": price,
                "currency": "BRL",
                "confidence": round(score, 3),
                "method": "heuristic",
                # Campos internos para debug (removidos antes de retornar)
                "_debug_text": text[:80],
                "_debug_tag": parent.name,
                "_debug_classes": parent.get("class", []),
            })

    if not candidates:
        logger.warning("[Heurística] Nenhum candidato de preço encontrado na página.")
        return None

    # Ordena por score (maior primeiro) e retorna o melhor
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    best = candidates[0]

    logger.info(
        f"[Heurística] Melhor candidato: R$ {best['price']:.2f} "
        f"(score={best['confidence']:.2f}, "
        f"tag=<{best['_debug_tag']}>, "
        f"classes={best['_debug_classes']})"
    )

    return {k: v for k, v in best.items() if not k.startswith("_")}


def _in_ignored_section(element: Tag) -> bool:
    """
    Verifica se o elemento está dentro de uma seção que deve ser ignorada.
    Percorre os ancestrais analisando id e class.
    """
    for ancestor in element.parents:
        if not isinstance(ancestor, Tag):
            continue
        id_val = (ancestor.get("id") or "").lower()
        class_val = " ".join(ancestor.get("class") or []).lower()
        combined = f"{id_val} {class_val}"
        if any(kw in combined for kw in _IGNORE_SECTIONS):
            return True
    return False


def _score_candidate(price: float, element: Tag, text: str) -> float:
    """
    Atribui uma pontuação (0.0 – 1.0) ao candidato com base em sinais
    heurísticos de que é o preço principal do produto.

    Quanto maior o score, mais provável que seja o preço correto.
    """
    score = 0.30  # Pontuação base

    tag = element.name.lower() if element.name else ""
    class_str = " ".join(element.get("class") or []).lower()

    # ── Bônus por tipo de tag ────────────────────────────────────────────
    if tag in ("h1", "h2", "strong", "b"):
        score += 0.25
    elif tag in ("span", "div", "p", "ins"):
        score += 0.10

    # ── Bônus por classe CSS sugestiva de preço principal ───────────────
    if any(kw in class_str for kw in _PRICE_SIGNAL_CLASSES):
        score += 0.20

    # ── Bônus por "R$" explícito no texto ───────────────────────────────
    if re.search(r"R\$", text, re.IGNORECASE):
        score += 0.10

    # ── Penalidade por preço fora da faixa típica de hardware ───────────
    if not (30.0 <= price <= 60_000.0):
        score -= 0.20

    # ── Penalidade leve para preços suspeitosamente redondos ────────────
    if price % 100 == 0 and price > 1000:
        score -= 0.05

    return max(0.0, min(1.0, score))
