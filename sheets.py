"""
sheets.py
---------
Módulo responsável por toda a integração com o Google Sheets:
- Autenticação via Service Account
- Verificação de registros duplicados
- Inserção de novos registros
- Consulta ao histórico de preços
"""

import logging
from typing import Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# Escopos necessários para ler e escrever no Google Sheets e Drive
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# Cabeçalho padrão da planilha (ordem das colunas)
SHEET_HEADERS = [
    "data",
    "produto",
    "loja",
    "preco",
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

    Parâmetros
    ----------
    credentials_file  : Caminho para o arquivo credentials.json baixado do
                        Google Cloud Console.
    spreadsheet_name  : Nome exato da planilha no Google Drive (case-sensitive).

    Raises
    ------
    FileNotFoundError        : Se credentials_file não existir.
    gspread.SpreadsheetNotFound : Se a planilha não for encontrada ou não tiver
                                  sido compartilhada com a service account.
    """
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_file, SCOPES
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open(spreadsheet_name)
        sheet = spreadsheet.sheet1

        # Garante que o cabeçalho existe na primeira linha
        first_row = sheet.row_values(1)
        if first_row != SHEET_HEADERS:
            if not first_row:
                # Planilha vazia: insere cabeçalho
                sheet.insert_row(SHEET_HEADERS, index=1)
                logger.info("Cabeçalho criado na planilha.")
            else:
                # Cabeçalho divergente: avisa mas continua
                logger.warning(
                    f"Cabeçalho da planilha diverge do esperado. "
                    f"Encontrado: {first_row} | Esperado: {SHEET_HEADERS}"
                )

        logger.info(f"Conectado à planilha '{spreadsheet_name}' com sucesso.")
        return sheet

    except FileNotFoundError:
        logger.error(
            f"Arquivo de credenciais '{credentials_file}' não encontrado. "
            "Verifique o caminho em config.json."
        )
        raise
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(
            f"Planilha '{spreadsheet_name}' não encontrada. "
            "Certifique-se de que ela existe e foi compartilhada com o e-mail "
            "da service account (client_email no credentials.json)."
        )
        raise
    except Exception as exc:
        logger.error(f"Erro inesperado ao conectar ao Google Sheets: {exc}")
        raise


def is_duplicate(sheet: gspread.Worksheet, today: str, product_name: str) -> bool:
    """
    Verifica se já existe um registro para `product_name` na data `today`.

    Retorna True se duplicado, False caso contrário.
    Em caso de erro, retorna False para não bloquear a execução.
    """
    try:
        records = sheet.get_all_records()
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


def get_min_price(sheet: gspread.Worksheet, product_name: str) -> Optional[float]:
    """
    Retorna o menor preço já registrado para `product_name` na planilha.
    Retorna None se não houver histórico.
    """
    try:
        records = sheet.get_all_records()
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
        logger.error(f"Erro ao calcular preço mínimo histórico: {exc}")
        return None


def append_row(
    sheet: gspread.Worksheet,
    data: dict,
    min_price: Optional[float],
) -> bool:
    """
    Adiciona uma nova linha na planilha com os dados do produto.

    Parâmetros
    ----------
    sheet     : Worksheet do gspread
    data      : Dict com chaves: data, produto, loja, preco, url
    min_price : Menor preço histórico (pode ser igual ao preço atual
                se for o primeiro registro)

    Retorna True se bem-sucedido, False em caso de erro.
    """
    try:
        row = [
            data["data"],
            data["produto"],
            data["loja"],
            # Formata o preço como número com 2 casas decimais
            round(float(data["preco"]), 2),
            data["url"],
            round(float(min_price), 2) if min_price is not None else round(float(data["preco"]), 2),
        ]
        # USER_ENTERED permite que o Sheets interprete números como tal
        sheet.append_row(row, value_input_option="USER_ENTERED")

        preco_fmt = f"R$ {data['preco']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        logger.info(f"Linha adicionada: [{data['produto']}] {preco_fmt} em {data['data']}")
        return True

    except Exception as exc:
        logger.error(f"Erro ao gravar linha na planilha: {exc}")
        return False


def get_price_history(sheet: gspread.Worksheet, product_name: str) -> list:
    """
    Retorna uma lista de dicts com todo o histórico de preços de um produto.
    Cada item contém: data, preco.
    """
    try:
        records = sheet.get_all_records()
        history = [
            {"data": r["data"], "preco": float(r["preco"])}
            for r in records
            if str(r.get("produto", "")).strip() == product_name
            and r.get("preco") not in ("", None)
        ]
        return sorted(history, key=lambda x: x["data"])
    except Exception as exc:
        logger.error(f"Erro ao buscar histórico de '{product_name}': {exc}")
        return []
