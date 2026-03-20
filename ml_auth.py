#!/usr/bin/env python3
"""
ml_auth.py
----------
Faz a autenticação OAuth2 com o Mercado Livre (Authorization Code + PKCE)
e salva o access_token + refresh_token no config.json.

Só precisa rodar UMA VEZ. Depois disso, mercadolivre.py renova o token
automaticamente usando o refresh_token.

Como usar:
    python ml_auth.py
"""

import base64
import hashlib
import json
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


def _generate_pkce() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge) for PKCE."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode("utf-8").rstrip("=")
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return code_verifier, code_challenge


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"[ERRO] config.json não encontrado em {CONFIG_FILE}")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    cfg = load_config()

    app_id = cfg.get("mercadolivre_app_id")
    secret = cfg.get("mercadolivre_secret_key")
    redirect_uri = cfg.get("mercadolivre_redirect_uri")

    if not app_id or not secret:
        print("[ERRO] 'mercadolivre_app_id' ou 'mercadolivre_secret_key' não encontrados no config.json")
        sys.exit(1)

    if not redirect_uri:
        print("Qual é a URI de redirect cadastrada no seu app do Mercado Livre?")
        print("  Ex: https://79dc-167-250-154-168.ngrok-free.app/callback")
        redirect_uri = input("URI de redirect: ").strip()
        if not redirect_uri:
            sys.exit(1)
        cfg["mercadolivre_redirect_uri"] = redirect_uri
        save_config(cfg)

    # Generate PKCE pair
    code_verifier, code_challenge = _generate_pkce()

    # Build authorization URL with PKCE
    params = {
        "response_type": "code",
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_link = AUTH_URL + "?" + urlencode(params)

    print()
    print("=" * 60)
    print("  AUTENTICAÇÃO MERCADO LIVRE")
    print("=" * 60)
    print()
    print("1. Abrindo o browser para autorização...")
    print(f"   Se não abrir automaticamente, acesse:")
    print(f"   {auth_link}")
    print()
    webbrowser.open(auth_link)

    print("2. Após autorizar, você será redirecionado para uma URL")
    print("   (a página pode dar erro 404 — isso é normal).")
    print()
    print("3. Copie a URL COMPLETA da barra de endereços do navegador")
    print("   e cole aqui abaixo:")
    print()

    redirected_url = input("URL completa após o redirect: ").strip()

    # Extract code from the redirected URL
    try:
        parsed = urlparse(redirected_url)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
    except Exception:
        code = None

    if not code:
        print()
        print("[ERRO] Não foi possível extrair o código da URL fornecida.")
        print("Certifique-se de copiar a URL COMPLETA (com ?code=... no final).")
        sys.exit(1)

    print()
    print("4. Trocando o código pelo token...")

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": app_id,
                "client_secret": secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except requests.RequestException as exc:
        print(f"[ERRO] Falha ao obter token: {exc}")
        if hasattr(exc, "response") and exc.response is not None:
            print("Resposta:", exc.response.text[:300])
        sys.exit(1)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        print(f"[ERRO] token não encontrado na resposta: {token_data}")
        sys.exit(1)

    # Save tokens to config.json
    cfg["mercadolivre_access_token"] = access_token
    if refresh_token:
        cfg["mercadolivre_refresh_token"] = refresh_token
    save_config(cfg)

    print()
    print("=" * 60)
    print("  ✓ Autenticação concluída com sucesso!")
    print("=" * 60)
    print()
    print(f"  Access token salvo em config.json")
    if refresh_token:
        print(f"  Refresh token salvo — renovação automática ativada")
    else:
        print(f"  ⚠  Refresh token não recebido.")
        print(f"     Ative 'Refresh Token' no painel do seu app ML e rode novamente.")
    print()
    print("  Agora rode: python search_cli.py \"RTX 4070\"")
    print()


if __name__ == "__main__":
    main()


BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        print(f"[ERRO] config.json não encontrado em {CONFIG_FILE}")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    cfg = load_config()

    app_id = cfg.get("mercadolivre_app_id")
    secret = cfg.get("mercadolivre_secret_key")
    redirect_uri = cfg.get("mercadolivre_redirect_uri")

    if not app_id or not secret:
        print("[ERRO] 'mercadolivre_app_id' ou 'mercadolivre_secret_key' não encontrados no config.json")
        sys.exit(1)

    if not redirect_uri:
        print("Qual é a URI de redirect cadastrada no seu app do Mercado Livre?")
        print("  Ex: https://79dc-167-250-154-168.ngrok-free.app/callback")
        redirect_uri = input("URI de redirect: ").strip()
        if not redirect_uri:
            sys.exit(1)
        cfg["mercadolivre_redirect_uri"] = redirect_uri
        save_config(cfg)

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": app_id,
        "redirect_uri": redirect_uri,
    }
    auth_link = AUTH_URL + "?" + urlencode(params)

    print()
    print("=" * 60)
    print("  AUTENTICAÇÃO MERCADO LIVRE")
    print("=" * 60)
    print()
    print("1. Abrindo o browser para autorização...")
    print(f"   Se não abrir automaticamente, acesse:")
    print(f"   {auth_link}")
    print()
    webbrowser.open(auth_link)

    print("2. Após autorizar, você será redirecionado para uma URL")
    print("   (a página pode dar erro 404 — isso é normal).")
    print()
    print("3. Copie a URL COMPLETA da barra de endereços do navegador")
    print("   e cole aqui abaixo:")
    print()

    redirected_url = input("URL completa após o redirect: ").strip()

    # Extract code from the redirected URL
    try:
        parsed = urlparse(redirected_url)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
    except Exception:
        code = None

    if not code:
        print()
        print("[ERRO] Não foi possível extrair o código da URL fornecida.")
        print("Certifique-se de copiar a URL COMPLETA (com ?code=... no final).")
        sys.exit(1)

    print()
    print("4. Trocando o código pelo token...")

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": app_id,
                "client_secret": secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except requests.RequestException as exc:
        print(f"[ERRO] Falha ao obter token: {exc}")
        if hasattr(exc, "response") and exc.response is not None:
            print("Resposta:", exc.response.text[:300])
        sys.exit(1)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        print(f"[ERRO] token não encontrado na resposta: {token_data}")
        sys.exit(1)

    # Save tokens to config.json
    cfg["mercadolivre_access_token"] = access_token
    if refresh_token:
        cfg["mercadolivre_refresh_token"] = refresh_token
    save_config(cfg)

    print()
    print("=" * 60)
    print("  ✓ Autenticação concluída com sucesso!")
    print("=" * 60)
    print()
    print(f"  Access token salvo em config.json")
    if refresh_token:
        print(f"  Refresh token salvo — renovação automática ativada")
    else:
        print(f"  ⚠  Refresh token não recebido.")
        print(f"     Ative 'Refresh Token' no painel do seu app ML e rode novamente.")
    print()
    print("  Agora rode: python search_cli.py \"RTX 4070\"")
    print()


if __name__ == "__main__":
    main()
