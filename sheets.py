"""
sheets.py
---------
MÃ³dulo responsÃ¡vel por toda a integraÃ§Ã£o com o Google Sheets:
- AutenticaÃ§Ã£o via Service Account
- VerificaÃ§Ã£o de registros duplicados
- InserÃ§Ã£o de novos registros
- Consulta ao histÃ³rico de preÃ§os
"""

import logging
from typing import Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# Escopos necessÃ¡rios para ler e escrever no Google Sheets e Drive
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# CabeÃ§alho padrÃ£o da planilha (ordem das colunas)
SHEET_HEADERS = [
    "data",
    "produto",
    "loja",
    "preco",               # preÃ§o promocional
    "preco_sem_promocao",  # preÃ§o sem desconto / de lista
    "preco_cartao",        # total da compra no cartÃ£o
    "preco_parcelado",     # valor de cada parcela
    "parcelas",            # nÃºmero de parcelas
    "url",
    "preco_minimo_historico",
]


def connect_to_sheets(
    credentials_file: str,
    spreadsheet_name: str,
) -> gspread.Worksheet:
    """
    Autentica usando uma Service Account e retorna a primeira aba (worksheet)
    da planilha especificada.

    ParÃ¢metros
    ----------
    credentials_file  : Caminho para o arquivo credentials.json baixado do
                        Google Cloud Console.
    spreadsheet_name  : Nome exato da planilha no Google Drive (case-sensitive).

    Raises
    ------
    FileNotFoundError        : Se credentials_file nÃ£o existir.
    gspread.SpreadsheetNotFound : Se a planilha nÃ£o for encontrada ou nÃ£o tiver
                                  sido compartilhada com a service account.
    """
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_file, SCOPES
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open(spreadsheet_name)
        sheet = spreadsheet.sheet1

        # Garante que o cabeÃ§alho existe na primeira linha
        first_row = sheet.row_values(1)
        if first_row != SHEET_HEADERS:
            if not first_row:
                # Planilha vazia: insere cabeÃ§alho
                sheet.insert_row(SHEET_HEADERS, index=1)
                logger.info("CabeÃ§alho criado na planilha.")
            else:
                # CabeÃ§alho divergente: avisa mas continua
                logger.warning(
                    f"CabeÃ§alho da planilha diverge do esperado. "
                    f"Encontrado: {first_row} | Esperado: {SHEET_HEADERS}"
                )

        logger.info(f"Conectado Ã  planilha '{spreadsheet_name}' com sucesso.")
        return sheet

    except FileNotFoundError:
        logger.error(
            f"Arquivo de credenciais '{credentials_file}' nÃ£o encontrado. "
            "Verifique o caminho em config.json."
        )
        raise
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(
            f"Planilha '{spreadsheet_name}' nÃ£o encontrada. "
            "Certifique-se de que ela existe e foi compartilhada com o e-mail "
            "da service account (client_email no credentials.json)."
        )
        raise
    except Exception as exc:
        logger.error(f"Erro inesperado ao conectar ao Google Sheets: {exc}")
        raise


def _get_records(sheet: gspread.Worksheet) -> list[dict]:
    """
    Alternativa robusta a get_all_records() que nÃ£o falha quando hÃ¡
    colunas com nomes duplicados na planilha.
    Usa get_all_values() e faz o zip manualmente usando a primeira linha
    como cabeÃ§alho.
    """
    rows = sheet.get_all_values()
    if not rows:
        return []
    headers = rows[0]
    # Para colunas repetidas, sufixar com _2, _3, etc para nÃ£o perder dados
    seen: dict[str, int] = {}
    safe_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            safe_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 1
            safe_headers.append(h)
    return [dict(zip(safe_headers, row)) for row in rows[1:]]


def is_duplicate(sheet: gspread.Worksheet, today: str, product_name: str) -> bool:
    """
    Verifica se jÃ¡ existe um registro para `product_name` na data `today`.

    Retorna True se duplicado, False caso contrÃ¡rio.
    Em caso de erro, retorna False para nÃ£o bloquear a execuÃ§Ã£o.
    """
    try:
        records = _get_records(sheet)
        for record in records:
            if (
                str(record.get("data", "")).strip() == today
                and str(record.get("produto", "")).strip() == product_name
            ):
                return True
        return False
    except Exception as exc:
        logger.error(f"Erro ao verificar duplicatas: {exc}")
        return False


def is_duplicate_shopping(
    sheet: gspread.Worksheet,
    today: str,
    product_name: str,
    store: str,
) -> bool:
    """
    VersÃ£o para modo shopping: verifica se jÃ¡ existe registro para
    (data, produto, loja). Permite mÃºltiplas lojas por produto por dia.

    Retorna True se duplicado, False caso contrÃ¡rio.
    """
    try:
        records = _get_records(sheet)
        for record in records:
            if (
                str(record.get("data", "")).strip() == today
                and str(record.get("produto", "")).strip() == product_name
                and str(record.get("loja", "")).strip() == store
            ):
                return True
        return False
    except Exception as exc:
        logger.error(f"Erro ao verificar duplicatas (shopping): {exc}")
        return False


def get_min_price(sheet: gspread.Worksheet, product_name: str) -> Optional[float]:
    """
    Retorna o menor preÃ§o jÃ¡ registrado para `product_name` na planilha.
    Retorna None se nÃ£o houver histÃ³rico.
    """
    try:
        records = _get_records(sheet)
        prices = []
        for record in records:
            if str(record.get("produto", "")).strip() == product_name:
                raw = record.get("preco", "")
                try:
                    prices.append(float(raw))
                except (ValueError, TypeError):
                    pass
        return min(prices) if prices else None
    except Exception as exc:
        logger.error(f"Erro ao calcular preÃ§o mÃ­nimo histÃ³rico: {exc}")
        return None


def append_row(
    sheet: gspread.Worksheet,
    data: dict,
    min_price: Optional[float],
) -> bool:
    """
    Adiciona uma nova linha na planilha com os dados do produto.

    ParÃ¢metros
    ----------
    sheet     : Worksheet do gspread
    data      : Dict com chaves: data, produto, loja, preco, url
    min_price : Menor preÃ§o histÃ³rico (pode ser igual ao preÃ§o atual
                se for o primeiro registro)

    Retorna True se bem-sucedido, False em caso de erro.
    """
    try:
        def _fmt(val) -> str:
            """Formata float com 2 casas ou retorna string vazia para None."""
            if val is None:
                return ""
            try:
                return round(float(val), 2)
            except (TypeError, ValueError):
                return ""

        row = [
            data["data"],
            data["produto"],
            data["loja"],
            # Formata o preÃ§o como nÃºmero com 2 casas decimais
            round(float(data["preco"]), 2),
            _fmt(data.get("preco_sem_promocao")),
            _fmt(data.get("preco_cartao")),
            _fmt(data.get("preco_parcelado")),
            data.get("parcelas") or "",
            data["url"],
            round(float(min_price), 2) if min_price is not None else round(float(data["preco"]), 2),
        ]
        # USER_ENTERED permite que o Sheets interprete nÃºmeros como tal
        sheet.append_row(row, value_input_option="USER_ENTERED")

        preco_fmt = f"R$ {data['preco']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        logger.info(f"Linha adicionada: [{data['produto']}] {preco_fmt} em {data['data']}")
        return True

    except Exception as exc:
        logger.error(f"Erro ao gravar linha na planilha: {exc}")
        return False


def get_price_history(sheet: gspread.Worksheet, product_name: str) -> list:
    """
    Retorna uma lista de dicts com todo o histÃ³rico de preÃ§os de um produto.
    Cada item contÃ©m: data, preco.
    """
    try:
        records = _get_records(sheet)
        history = [
            {"data": r["data"], "preco": float(r["preco"])}
            for r in records
            if str(r.get("produto", "")).strip() == product_name
            and r.get("preco") not in ("", None)
        ]
        return sorted(history, key=lambda x: x["data"])
    except Exception as exc:
        logger.error(f"Erro ao buscar histÃ³rico de '{product_name}': {exc}")
        return []
