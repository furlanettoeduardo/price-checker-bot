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
import subprocess
import sys
import time
from pathlib import Path
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

# Tenta importar playwright + playwright-stealth — fallback for JS-rendered / Cloudflare UAM
try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # ImportError, OSError ou falha de inicialização
    _PLAYWRIGHT_AVAILABLE = False
    logger.debug("playwright não instalado ou falhou ao inicializar — fallback JS desabilitado.")

try:
    from playwright_stealth import Stealth as _Stealth
    _STEALTH_AVAILABLE = True
except Exception:
    _STEALTH_AVAILABLE = False
    logger.debug("playwright-stealth não instalado — modo stealth desabilitado.")

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
    use_playwright: bool = False,
) -> Optional[BeautifulSoup]:
    """
    Baixa a página HTML e retorna um objeto BeautifulSoup.

    Parâmetros
    ----------
    url            : URL da página
    timeout        : Timeout da requisição (segundos)
    min_delay      : Delay mínimo entre requisições (segundos)
    max_delay      : Delay máximo entre requisições (segundos)
    max_retries    : Tentativas adicionais em caso de erro 5xx ou 429
    use_cache      : Se True, reutiliza HTML já baixado nesta execução
    use_playwright : Se True, usa Playwright+stealth diretamente (ignora requests);
                     se False, Playwright é acionado apenas como fallback quando
                     tanto requests quanto cloudscraper falham.

    Retorna
    -------
    BeautifulSoup ou None em caso de falha permanente.
    """
    if use_cache and url in _cache:
        logger.debug(f"Cache hit — não baixará novamente: {url}")
        return _cache[url]

    # Playwright como método primário quando explicitamente solicitado
    if use_playwright:
        soup = _try_playwright(url)
        if soup is not None:
            if use_cache:
                _cache[url] = soup
            return soup
        logger.warning(f"[Playwright] Falhou como método primário para: {url}")
        return None

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
            # 403 geralmente indica Cloudflare — tenta via cloudscraper e depois playwright
            if status == 403:
                soup = _try_cloudscraper(url)
                if soup is not None:
                    if use_cache:
                        _cache[url] = soup
                    return soup
                # cloudscraper também falhou — tenta playwright (Cloudflare UAM)
                logger.info(f"cloudscraper falhou — tentando Playwright para: {url}")
                soup = _try_playwright(url)
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
            "Tentando Playwright como próximo passo."
        )
        return None
    except Exception as exc:
        logger.warning(f"[cloudscraper] Falha em {url}: {exc}")
        return None


def _install_playwright_browser() -> bool:
    """
    Tenta instalar o Chromium via o driver do Playwright embutido ou do PATH.
    Útil quando o binário não está presente na máquina de destino.
    Retorna True se o install pareceu bem-sucedido.
    """
    logger.warning("[Playwright] Binário do Chromium não encontrado. Tentando instalar automaticamente...")

    # ── Modo frozen (PyInstaller .exe) ──────────────────────────────────────
    # O Playwright espera os browsers em _internal/playwright/driver/package/.local-browsers/
    # Tenta copiar de %LOCALAPPDATA%\ms-playwright\ (onde 'playwright install' baixa)
    if getattr(sys, "frozen", False):
        import os
        import shutil as _shutil
        ms_pw = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        pkg_browsers = Path(sys.executable).parent / "_internal" / "playwright" / "driver" / "package" / ".local-browsers"
        pkg_browsers.mkdir(parents=True, exist_ok=True)

        if ms_pw.is_dir():
            copied = False
            for item in ms_pw.iterdir():
                if item.is_dir() and item.name.startswith(("chromium_headless_shell", "chromium", "ffmpeg", "winldd")):
                    dst = pkg_browsers / item.name
                    if not dst.exists():
                        logger.info(f"[Playwright] Copiando {item.name} para o bundle...")
                        _shutil.copytree(str(item), str(dst))
                        copied = True
            if copied:
                logger.info("[Playwright] Browsers copiados com sucesso.")
                return True

        # ms-playwright não encontrado ou vazio — tenta baixar via playwright driver embutido
        internal_driver = Path(sys.executable).parent / "_internal" / "playwright" / "driver"
        for cli in [internal_driver / "playwright.cmd", internal_driver / "playwright.exe"]:
            if cli.exists():
                import os as _os
                env = _os.environ.copy()
                env["PLAYWRIGHT_BROWSERS_PATH"] = str(pkg_browsers.parent)
                try:
                    result = subprocess.run(
                        [str(cli), "install", "chromium"],
                        capture_output=True, text=True, timeout=300, env=env
                    )
                    if result.returncode == 0:
                        logger.info("[Playwright] Chromium instalado via driver embutido.")
                        return True
                except Exception as exc:
                    logger.debug(f"[Playwright] Falha ao instalar via {cli}: {exc}")

        logger.error("[Playwright] Não foi possível instalar o Chromium automaticamente no bundle.")
        return False

    # ── Modo desenvolvimento ─────────────────────────────────────────────────
    candidates = []
    import shutil as _shutil
    pw_in_path = _shutil.which("playwright")
    if pw_in_path:
        candidates.append(Path(pw_in_path))
    candidates.append(None)  # sentinela → usa `python -m playwright`

    for candidate in candidates:
        try:
            if candidate is None:
                cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            else:
                cmd = [str(candidate), "install", "chromium"]

            logger.info(f"[Playwright] Rodando: {' '.join(str(c) for c in cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info("[Playwright] Chromium instalado com sucesso.")
                return True
            logger.warning(f"[Playwright] Install retornou {result.returncode}: {result.stderr[:200]}")
        except Exception as exc:
            logger.debug(f"[Playwright] Falha ao tentar instalar com {candidate}: {exc}")

    logger.error("[Playwright] Não foi possível instalar o Chromium automaticamente.")
    return False


def _try_playwright(url: str, timeout_ms: int = 30_000) -> Optional[BeautifulSoup]:
    """
    Tenta baixar a página usando Playwright com modo stealth ativado.

    Estratégia:
    - Importa playwright inline a cada chamada para evitar flags obsoletos.
    - Lança Chromium em modo headless com perfil realista de navegador.
    - Aplica playwright-stealth para ocultar fingerprints de automação
      (navigator.webdriver, plugins, etc.) — eficaz contra Cloudflare JS Challenge
      e Under Attack Mode.
    - Aguarda 'networkidle' para garantir que o JS da página foi executado
      antes de capturar o HTML (resolve sites com preços renderizados via JS).

    Retorna BeautifulSoup em caso de sucesso, None caso contrário.
    """
    # Import inline: evita depender de flag de módulo que pode ter falhado
    # transitoriamente na inicialização (problema comum no Windows).
    try:
        from playwright.sync_api import sync_playwright as _pw
    except Exception:
        logger.warning(
            f"Playwright não instalado — não foi possível carregar JS para: {url}. "
            "Execute: pip install playwright && playwright install chromium"
        )
        return None

    try:
        from playwright_stealth import Stealth as _StealthCls
        _has_stealth = True
    except Exception:
        _has_stealth = False

    logger.info(f"[Playwright] Iniciando browser headless para: {url}")
    try:
        with _pw() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()

            # Aplica stealth para ocultar sinais de automação
            if _has_stealth:
                _StealthCls().apply_stealth_sync(page)
                logger.debug("[Playwright] Modo stealth ativado.")
            else:
                logger.debug("[Playwright] playwright-stealth não disponível — stealth parcial.")

            try:
                response = page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            except Exception as exc:
                # Alguns sites mantêm conexões abertas e nunca chegam a networkidle.
                # Tenta novamente com domcontentloaded para não travar o scraping.
                logger.warning(
                    f"[Playwright] networkidle falhou ({exc}). Tentando domcontentloaded: {url}"
                )
                response = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            if response is None or response.status >= 400:
                status = response.status if response else "?"
                logger.warning(f"[Playwright] Status {status} para: {url}")
                browser.close()
                return None

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        logger.info(f"[Playwright] Página obtida com sucesso: {url}")
        return soup

    except Exception as exc:
        exc_str = str(exc)
        # Chromium binary missing — tenta instalar e rodar uma segunda vez
        if "Executable doesn't exist" in exc_str and _install_playwright_browser():
            logger.info(f"[Playwright] Re-tentando após instalação do Chromium: {url}")
            try:
                with _pw() as pw:
                    browser = pw.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                    )
                    context = browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/122.0.0.0 Safari/537.36"
                        ),
                        locale="pt-BR",
                        timezone_id="America/Sao_Paulo",
                        viewport={"width": 1366, "height": 768},
                    )
                    page = context.new_page()
                    if _has_stealth:
                        _StealthCls().apply_stealth_sync(page)
                    try:
                        response = page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                    except Exception:
                        response = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    if response is not None and response.status < 400:
                        html = page.content()
                        browser.close()
                        soup = BeautifulSoup(html, "lxml")
                        logger.info(f"[Playwright] Página obtida com sucesso (retry): {url}")
                        return soup
                    browser.close()
            except Exception as retry_exc:
                logger.warning(f"[Playwright] Falha no retry após install: {retry_exc}")

        logger.warning(f"[Playwright] Falha em {url}: {exc}")
        return None
