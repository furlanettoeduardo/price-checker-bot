"""
scraper.py
----------
Módulo responsável por acessar as páginas dos produtos e extrair os preços.
Suporta múltiplos seletores CSS, normalização de preços em formato brasileiro
e tratamento robusto de erros.
"""

import logging
import random
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Headers que imitam um navegador real para evitar bloqueios básicos de anti-bot
# ---------------------------------------------------------------------------
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Delay mínimo e máximo (em segundos) entre requisições para não sobrecarregar
# os servidores e reduzir risco de bloqueio.
MIN_DELAY_SEC = 1.5
MAX_DELAY_SEC = 4.0


def normalize_price(raw: str) -> Optional[float]:
    """
    Converte uma string de preço no formato brasileiro para float.

    Exemplos de entrada aceitos:
        "R$ 1.234,56"  → 1234.56
        "R$2.099,90"   → 2099.90
        "1234,56"      → 1234.56
        "1234.56"      → 1234.56

    Retorna None se a conversão falhar.
    """
    if not raw:
        return None

    # Remove espaços, quebras de linha e o caractere de espaço não-separável
    cleaned = raw.strip().replace("\xa0", " ").replace("\n", "").replace("\t", "")

    # Extrai o primeiro número que contenha dígitos, ponto e/ou vírgula
    match = re.search(r"[\d.,]+", cleaned)
    if not match:
        return None

    number_str = match.group()

    # Formato brasileiro: "1.234,56" → separador de milhar é ".", decimal é ","
    if "," in number_str and "." in number_str:
        # Remove pontos (milhar) e troca vírgula por ponto (decimal)
        number_str = number_str.replace(".", "").replace(",", ".")
    elif "," in number_str:
        # Apenas vírgula → é o separador decimal
        number_str = number_str.replace(",", ".")

    try:
        value = float(number_str)
        # Sanidade: preços válidos de hardware geralmente ficam entre R$ 1 e R$ 100.000
        if not (1.0 <= value <= 100_000.0):
            logger.warning(f"Preço fora do intervalo esperado: {value} (texto original: '{raw}')")
        return value
    except ValueError:
        logger.warning(f"Não foi possível converter '{number_str}' para float (texto original: '{raw}')")
        return None


def fetch_page(url: str, timeout: int = 20) -> Optional[BeautifulSoup]:
    """
    Faz o download da página HTML e retorna um objeto BeautifulSoup.

    Inclui:
    - Delay aleatório para comportamento mais humano
    - Tratamento de todos os erros comuns de requisição HTTP
    - Retorna None em caso de falha (em vez de lançar exceção)
    """
    # Delay aleatório entre requisições
    delay = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
    logger.debug(f"Aguardando {delay:.1f}s antes de acessar {url}")
    time.sleep(delay)

    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        response.raise_for_status()  # Lança HTTPError para status 4xx/5xx
        return BeautifulSoup(response.text, "html.parser")

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        logger.error(f"Erro HTTP {status} ao acessar: {url}")
    except requests.exceptions.ConnectionError:
        logger.error(f"Falha de conexão ao acessar: {url}")
    except requests.exceptions.Timeout:
        logger.error(f"Timeout ({timeout}s) ao acessar: {url}")
    except requests.exceptions.RequestException as exc:
        logger.error(f"Erro inesperado de requisição em {url}: {exc}")

    return None


def extract_price(url: str, selectors: list) -> Optional[float]:
    """
    Tenta extrair o preço de um produto em uma URL usando uma lista de
    seletores CSS (tentados em ordem até o primeiro sucesso).

    Parâmetros
    ----------
    url       : URL da página do produto
    selectors : Lista de seletores CSS, do mais específico para o mais genérico

    Retorna o preço como float, ou None se nenhum seletor funcionou.
    """
    if not selectors:
        logger.error("Lista de seletores vazia para URL: " + url)
        return None

    soup = fetch_page(url)
    if soup is None:
        return None

    for selector in selectors:
        try:
            element = soup.select_one(selector)
            if element is None:
                logger.debug(f"Seletor '{selector}' não encontrou elemento.")
                continue

            raw_text = element.get_text(separator=" ", strip=True)
            price = normalize_price(raw_text)

            if price is not None:
                logger.info(
                    f"✓ Preço extraído com seletor '{selector}': "
                    f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
                return price

            logger.warning(
                f"Seletor '{selector}' encontrou texto mas preço não extraído: '{raw_text}'"
            )

        except Exception as exc:
            logger.warning(f"Erro ao aplicar seletor '{selector}': {exc}")

    logger.error(f"Nenhum seletor funcionou para: {url}")
    logger.error(f"Seletores testados: {selectors}")
    return None
