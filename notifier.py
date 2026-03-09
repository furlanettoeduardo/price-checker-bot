"""
notifier.py
-----------
Módulo opcional para envio de alertas via Telegram.

Como configurar:
1. Crie um bot no Telegram conversando com @BotFather e obtenha o BOT_TOKEN.
2. Inicie uma conversa com seu bot e obtenha seu CHAT_ID via:
   https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
3. Preencha os campos "telegram" no config.json:
   {
     "telegram": {
       "enabled": true,
       "bot_token": "SEU_TOKEN_AQUI",
       "chat_id": "SEU_CHAT_ID_AQUI",
       "alert_on_new_low": true
     }
   }
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """
    Envia uma mensagem de texto para um chat do Telegram.

    Retorna True se bem-sucedido, False em caso de erro.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram não configurado (bot_token ou chat_id ausente).")
        return False

    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Alerta Telegram enviado para chat_id={chat_id}")
        return True
    except requests.exceptions.RequestException as exc:
        logger.error(f"Erro ao enviar mensagem Telegram: {exc}")
        return False


def notify_new_low(
    bot_token: str,
    chat_id: str,
    product_name: str,
    store: str,
    price: float,
    previous_min: Optional[float],
    url: str,
) -> bool:
    """
    Envia alerta quando um produto atinge seu menor preço histórico.

    Parâmetros
    ----------
    bot_token    : Token do bot Telegram
    chat_id      : ID do chat para enviar a mensagem
    product_name : Nome do produto
    store        : Nome da loja
    price        : Preço atual (novo mínimo)
    previous_min : Mínimo anterior (None se for o primeiro registro)
    url          : URL do produto

    Retorna True se a mensagem foi enviada, False caso contrário.
    """
    def fmt_brl(value: float) -> str:
        """Formata valor como moeda brasileira."""
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    preco_atual = fmt_brl(price)

    if previous_min is None or price < previous_min:
        if previous_min is not None:
            economia = fmt_brl(previous_min - price)
            msg = (
                f"🔥 *NOVO MÍNIMO HISTÓRICO!*\n\n"
                f"📦 *Produto:* {product_name}\n"
                f"🏪 *Loja:* {store}\n"
                f"💰 *Preço atual:* {preco_atual}\n"
                f"📉 *Mínimo anterior:* {fmt_brl(previous_min)}\n"
                f"💸 *Economia:* {economia}\n"
                f"🔗 [Ver produto]({url})"
            )
        else:
            msg = (
                f"✅ *Primeiro registro de preço!*\n\n"
                f"📦 *Produto:* {product_name}\n"
                f"🏪 *Loja:* {store}\n"
                f"💰 *Preço:* {preco_atual}\n"
                f"🔗 [Ver produto]({url})"
            )
        return send_telegram_message(bot_token, chat_id, msg)

    return False  # Não é novo mínimo, não envia alerta


def notify_error(
    bot_token: str,
    chat_id: str,
    product_name: str,
    store: str,
    error_msg: str,
) -> bool:
    """
    Envia alerta de erro ao tentar raspar o preço de um produto.
    Útil para ser notificado quando um seletor quebrar.
    """
    msg = (
        f"⚠️ *Erro ao verificar preço*\n\n"
        f"📦 *Produto:* {product_name}\n"
        f"🏪 *Loja:* {store}\n"
        f"❌ *Erro:* {error_msg}"
    )
    return send_telegram_message(bot_token, chat_id, msg)
