"""
html_fetcher.py
---------------
Responsável por baixar páginas HTML com:
  - Headers realistas de navegador para evitar bloqueios básicos
  - Delay aleatório entre requisições (comportamento humano)
  - Retry automático com backoff exponencial para erros 5xx/429
  - Cache em memória: mesma URL não é baixada duas vezes na mesma execução
"""

import logging
import random
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Tenta importar cloudscraper (bypass Cloudflare) — usado como fallback no 403
try:
    import cloudscraper as _cloudscraper_module
    _CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    _CLOUDSCRAPER_AVAILABLE = False
    logger.debug("cloudscraper não instalado — fallback Cloudflare desabilitado.")

# ── Headers que imitam Chrome no Windows ────────────────────────────────────
_HEADERS = {
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

# Cache em memória: url → BeautifulSoup (vida útil = 1 execução do bot)
_cache: dict[str, BeautifulSoup] = {}


def fetch_page(
    url: str,
    timeout: int = 20,
    min_delay: float = 1.5,
    max_delay: float = 4.0,
    max_retries: int = 2,
    use_cache: bool = True,
) -> Optional[BeautifulSoup]:
    """
    Baixa a página HTML e retorna um objeto BeautifulSoup.

    Parâmetros
    ----------
    url         : URL da página
    timeout     : Timeout da requisição (segundos)
    min_delay   : Delay mínimo entre requisições (segundos)
    max_delay   : Delay máximo entre requisições (segundos)
    max_retries : Tentativas adicionais em caso de erro 5xx ou 429
    use_cache   : Se True, reutiliza HTML já baixado nesta execução

    Retorna
    -------
    BeautifulSoup ou None em caso de falha permanente.
    """
    if use_cache and url in _cache:
        logger.debug(f"Cache hit — não baixará novamente: {url}")
        return _cache[url]

    # Delay aleatório para simular comportamento humano
    delay = random.uniform(min_delay, max_delay)
    logger.debug(f"Aguardando {delay:.1f}s antes de acessar: {url}")
    time.sleep(delay)

    for attempt in range(1, max_retries + 2):
        try:
            response = requests.get(url, headers=_HEADERS, timeout=timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            if use_cache:
                _cache[url] = soup
            logger.debug(f"Página baixada com sucesso: {url}")
            return soup

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            # Erros temporários (rate-limit, servidor sobrecarregado): retry com backoff
            if status in (429, 500, 502, 503, 504) and attempt <= max_retries:
                wait = 2 ** attempt  # 2s, 4s, 8s …
                logger.warning(
                    f"HTTP {status} em {url} — tentativa {attempt}/{max_retries}, "
                    f"aguardando {wait}s..."
                )
                time.sleep(wait)
                continue
            # 403 geralmente indica Cloudflare — tenta via cloudscraper
            if status == 403:
                soup = _try_cloudscraper(url)
                if soup is not None:
                    if use_cache:
                        _cache[url] = soup
                    return soup
            logger.error(f"Erro HTTP {status}: {url}")
            return None

        except requests.exceptions.ConnectionError:
            logger.error(f"Falha de conexão: {url}")
            return None

        except requests.exceptions.Timeout:
            logger.error(f"Timeout ({timeout}s): {url}")
            return None

        except requests.exceptions.RequestException as exc:
            logger.error(f"Erro inesperado em {url}: {exc}")
            return None

    return None


def clear_cache() -> None:
    """Limpa o cache de HTML em memória. Use entre execuções longas."""
    _cache.clear()
    logger.debug("Cache HTML limpo.")


def _try_cloudscraper(url: str) -> Optional[BeautifulSoup]:
    """
    Tenta baixar a página usando cloudscraper (bypass de Cloudflare JS challenge).
    Retorna BeautifulSoup em caso de sucesso, None caso contrário.
    """
    if not _CLOUDSCRAPER_AVAILABLE:
        logger.warning(
            f"HTTP 403 em {url} — instale 'cloudscraper' para tentar "
            "ignorar a proteção Cloudflare: pip install cloudscraper"
        )
        return None

    logger.info(f"HTTP 403 detectado — tentando cloudscraper para: {url}")
    try:
        scraper = _cloudscraper_module.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        response = scraper.get(url, timeout=25)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "lxml")
            logger.info(f"[cloudscraper] Página obtida com sucesso: {url}")
            return soup
        logger.warning(
            f"[cloudscraper] Código {response.status_code} para {url} — "
            "Cloudflare 'Under Attack Mode' provavelmente ativo. "
            "Considere usar Playwright para esta loja."
        )
        return None
    except Exception as exc:
        logger.warning(f"[cloudscraper] Falha em {url}: {exc}")
        return None
