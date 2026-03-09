# ðŸ¤– Price Checker Bot

Bot em Python que monitora preÃ§os de produtos em lojas brasileiras e registra o histÃ³rico em uma planilha do Google Sheets, com alertas via Telegram e interface grÃ¡fica completa.

---

## ðŸ“ Estrutura do Projeto

```
price-checker-bot/
â”‚
â”œâ”€â”€ app.py               # Interface grÃ¡fica principal (launcher + configuraÃ§Ãµes)
â”œâ”€â”€ main.py              # Orquestrador principal â€” pode ser chamado diretamente
â”œâ”€â”€ config_gui.py        # Editor de configuraÃ§Ã£o standalone (legado / opcional)
â”œâ”€â”€ sheets.py            # IntegraÃ§Ã£o com Google Sheets
â”œâ”€â”€ notifier.py          # Alertas via Telegram (opcional)
â”œâ”€â”€ config.json          # ConfiguraÃ§Ã£o de produtos e credenciais
â”œâ”€â”€ credentials.json     # âš ï¸ NÃƒO versionar â€” credenciais do Google
â”œâ”€â”€ requirements.txt     # DependÃªncias Python
â”œâ”€â”€ build.py             # Script de empacotamento para .exe (PyInstaller)
â”œâ”€â”€ build.bat            # Atalho: chama venv\Scripts\python.exe build.py
â”‚
â”œâ”€â”€ price_tracker/       # Pacote principal de extraÃ§Ã£o de preÃ§os
â”‚   â”œâ”€â”€ core/
â”‚   â”‚   â”œâ”€â”€ price_extractor.py   # Orquestrador das 4 camadas
â”‚   â”‚   â”œâ”€â”€ jsonld_parser.py     # Camada 1 â€” JSON-LD (dados estruturados)
â”‚   â”‚   â”œâ”€â”€ store_detector.py    # Detecta a loja pela URL
â”‚   â”‚   â””â”€â”€ heuristics.py        # Camada 4 â€” heurÃ­stica por pontuaÃ§Ã£o
â”‚   â”œâ”€â”€ scrapers/
â”‚   â”‚   â”œâ”€â”€ kabum.py             # Scraper dedicado Kabum
â”‚   â”‚   â”œâ”€â”€ pichau.py            # Scraper dedicado Pichau
â”‚   â”‚   â”œâ”€â”€ amazon.py            # Scraper dedicado Amazon
â”‚   â”‚   â””â”€â”€ terabyte.py          # Scraper dedicado Terabyte
â”‚   â””â”€â”€ utils/
â”‚       â”œâ”€â”€ html_fetcher.py      # HTTP com cache, retry, cloudscraper e Playwright
â”‚       â””â”€â”€ price_parser.py      # NormalizaÃ§Ã£o (R$ 3.499,90 â†’ 3499.90)
â”‚
â”œâ”€â”€ tests/               # Testes unitÃ¡rios (pytest)
â””â”€â”€ logs/
    â””â”€â”€ price_tracker.log
```

---

## ðŸ–¥ï¸ Interface GrÃ¡fica (app.py)

O `app.py` Ã© o ponto de entrada principal. ReÃºne em uma Ãºnica janela:

| Aba | FunÃ§Ã£o |
|-----|--------|
| **â–¶ Monitoramento** | BotÃ£o de execuÃ§Ã£o, barra de progresso e log em tempo real |
| **âš™ï¸ ConfiguraÃ§Ãµes** | Google Sheets, Telegram e opÃ§Ãµes gerais |
| **ðŸ“¦ Produtos** | Adicionar, editar, remover e reordenar produtos monitorados |
| **ðŸª Lojas** | Gerenciar o mapeamento domÃ­nio â†’ scraper dedicado |

Para iniciar:

```bash
# Com ambiente virtual ativo
python app.py
```

### Aba â–¶ Monitoramento

- Clique em **â–¶ Iniciar** para disparar a verificaÃ§Ã£o de todos os produtos.
- A barra de progresso mostra `[produto atual / total]`.
- O log exibe INFO, DEBUG, WARNING e ERROR com cores distintas.
- O bot roda em thread separada â€” a interface nÃ£o trava durante a execuÃ§Ã£o.

### Aba âš™ï¸ ConfiguraÃ§Ãµes

| Campo | DescriÃ§Ã£o |
|---|---|
| Arquivo de credenciais | Caminho para o `credentials.json` do Google |
| Nome da planilha | Nome exato da planilha no Google Drive |
| Ativar Telegram | Liga/desliga os alertas |
| Bot Token | Token fornecido pelo @BotFather |
| Chat ID | ID do chat para receber os alertas |
| Alertar em novo mÃ­nimo | Envia mensagem quando o preÃ§o bate recorde |

### Aba ðŸ“¦ Produtos

| AÃ§Ã£o | Como usar |
|---|---|
| **âž• Adicionar** | Abre formulÃ¡rio para cadastro de novo produto |
| **âœï¸ Editar** | Edita o produto selecionado (duplo clique tambÃ©m funciona) |
| **ðŸ—‘ï¸ Remover** | Remove com confirmaÃ§Ã£o |
| **â¬† / â¬‡ Reordenar** | Muda a ordem de verificaÃ§Ã£o |

Os **seletores CSS** sÃ£o opcionais â€” o bot tenta JSON-LD, scraper dedicado e heurÃ­stica automÃ¡tica antes de depender deles. O campo **`use_playwright`** ativa o browser headless para pÃ¡ginas com preÃ§os renderizados via JavaScript.

### Aba ðŸª Lojas

Gerencia o `STORE_MAP` em `price_tracker/core/store_detector.py`.

| AÃ§Ã£o | Como usar |
|---|---|
| **âž• Adicionar** | Informa domÃ­nio (ex: `americanas`) e ID do scraper |
| **ðŸ—‘ï¸ Remover** | Remove domÃ­nios personalizados (builtins sÃ£o protegidos) |
| **ðŸ“„ Criar / Abrir Template** | Cria `price_tracker/scrapers/<id>.py` com estrutura pronta |

**Fluxo para adicionar uma nova loja:**
1. Clique em **âž• Adicionar** na aba Lojas
2. Informe o fragmento do domÃ­nio (ex: `americanas`)
3. Deixe "Criar arquivo de scraper template" marcado e clique em **Adicionar**
4. Preencha os seletores no arquivo gerado
5. Clique em **Salvar configuraÃ§Ãµes** â€” o `store_detector.py` Ã© atualizado

### RodapÃ© â€” Salvar / Recarregar

VisÃ­vel nas abas ConfiguraÃ§Ãµes, Produtos e Lojas:
- **Salvar configuraÃ§Ãµes** â€” grava `config.json` e `store_detector.py`
- **Recarregar arquivo** â€” descarta alteraÃ§Ãµes e relÃª o arquivo do disco

---

## âš™ï¸ PrÃ©-requisitos (desenvolvimento)

- Python 3.10 ou superior
- Conta Google com acesso ao Google Cloud Console
- Conta Telegram com bot criado (opcional, para alertas)

---

## ðŸš€ InstalaÃ§Ã£o (modo desenvolvimento)

### 1. Clone o repositÃ³rio

```bash
git clone https://github.com/seu-usuario/price-checker-bot.git
cd price-checker-bot
```

### 2. Crie e ative o ambiente virtual

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependÃªncias

```bash
pip install -r requirements.txt
```

### 4. Instale o browser do Playwright

```bash
playwright install chromium
```

---

## ðŸ“¦ DistribuiÃ§Ã£o como .exe (Windows)

O projeto inclui um script de build que empacota tudo em `dist\PriceCheckerBot\` â€” incluindo o Chromium. NÃ£o Ã© necessÃ¡rio instalar Python ou dependÃªncias na mÃ¡quina de destino.

### PrÃ©-requisitos do build

1. Ambiente virtual configurado com todas as dependÃªncias instaladas
2. Chromium instalado: `venv\Scripts\playwright install chromium`

### Gerar o .exe

```bat
.\build.bat
```

O que o `build.py` faz:
1. Instala/atualiza o PyInstaller
2. Detecta e inclui os binÃ¡rios do Tcl/Tk automaticamente
3. Roda o PyInstaller com `--onedir` e todos os `--collect-all` necessÃ¡rios
4. Copia o Chromium de `%LOCALAPPDATA%\ms-playwright\` para dentro do bundle
5. Copia `config.json`, `credentials.json` e `icon.ico` para a pasta de saÃ­da

**SaÃ­da:** `dist\PriceCheckerBot\PriceCheckerBot.exe`

### Distribuir

```powershell
Compress-Archive -Path "dist\PriceCheckerBot" -DestinationPath "dist\PriceCheckerBot-v1.0.0.zip"
```

O usuÃ¡rio final coloca o `credentials.json` dentro da pasta `PriceCheckerBot\` e executa o `.exe`.

---

## ðŸ”‘ ConfiguraÃ§Ã£o do Google Sheets

### Passo 1 â€” Criar projeto no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Clique em **"Novo Projeto"** e dÃª um nome (ex: `price-checker-bot`)
3. Em **APIs e ServiÃ§os â†’ Biblioteca**, ative:
   - **Google Sheets API**
   - **Google Drive API**

### Passo 2 â€” Criar Service Account

1. VÃ¡ em **APIs e ServiÃ§os â†’ Credenciais**
2. Clique em **"Criar Credenciais" â†’ "Conta de ServiÃ§o"**
3. Preencha o nome (ex: `price-bot`) â†’ **"Criar e Continuar"** â†’ **"Concluir"**
4. Na lista, clique na service account criada
5. VÃ¡ em **"Chaves" â†’ "Adicionar Chave" â†’ "Criar nova chave"** â†’ formato **JSON**
6. Mova o arquivo baixado para a pasta raiz do projeto com o nome `credentials.json`

> âš ï¸ **Nunca suba o `credentials.json` para repositÃ³rios pÃºblicos!**

### Passo 3 â€” Criar e compartilhar a planilha

1. Acesse [sheets.google.com](https://sheets.google.com) e crie uma planilha
2. Nomeie-a exatamente como em `config.json` (`spreadsheet_name`)
3. Abra o `credentials.json`, copie o `client_email`
4. Na planilha, **Compartilhar** â†’ cole o e-mail â†’ permissÃ£o **Editor**

> O bot cria o cabeÃ§alho automaticamente na primeira execuÃ§Ã£o.

---

## ðŸ§± Arquitetura de ExtraÃ§Ã£o de PreÃ§os

O bot usa uma **estratÃ©gia em 4 camadas**, do mais ao menos confiÃ¡vel:

| Camada | MÃ©todo | ConfianÃ§a | DescriÃ§Ã£o |
|--------|---------|-----------|-----------|
| 1 | **JSON-LD** | 98% | `<script type="application/ld+json">` â€” mais estÃ¡vel |
| 2 | **Scraper dedicado** | 88â€“92% | Seletores CSS por loja (Kabum, Pichau, Amazon, Terabyte) |
| 3 | **Seletores do config** | 75% | Seletores definidos manualmente no `config.json` |
| 4 | **HeurÃ­stica** | 30â€“85% | Regex + pontuaÃ§Ã£o de elementos â€” fallback automÃ¡tico |

PÃ¡ginas que exigem JavaScript usam a camada extra **Playwright** (Chromium headless), ativada por `use_playwright: true` na configuraÃ§Ã£o do produto.

**Para adicionar suporte a uma nova loja programaticamente:**
1. Crie `price_tracker/scrapers/<loja>.py` com `extract(soup) -> dict | None`
2. Adicione a entrada em `STORE_MAP` no `store_detector.py`

---

## ðŸ“ ConfiguraÃ§Ã£o Manual do `config.json`

```json
{
  "google_sheets": {
    "credentials_file": "credentials.json",
    "spreadsheet_name": "Price Tracker"
  },

  "telegram": {
    "enabled": false,
    "bot_token": "SEU_BOT_TOKEN_AQUI",
    "chat_id": "SEU_CHAT_ID_AQUI",
    "alert_on_new_low": true
  },

  "products": [
    {
      "name": "RTX 4070 Super",
      "url": "https://www.kabum.com.br/produto/XXXXX/nome-do-produto",
      "price_selectors": [
        "h4.finalPrice",
        ".priceCard"
      ]
    },
    {
      "name": "Cockpit Speedtrack ST",
      "url": "https://loja.cockpitextremeracing.com.br/products/cockpit-speedtrack-st",
      "use_playwright": true
    }
  ]
}
```

### Campos do produto

| Campo | ObrigatÃ³rio | DescriÃ§Ã£o |
|---|---|---|
| `name` | âœ… | Nome do produto (identificador Ãºnico) |
| `url` | âœ… | URL completa da pÃ¡gina do produto |
| `price_selectors` | â˜ opcional | Lista de seletores CSS (camada 3 â€” pode ser omitida) |
| `use_playwright` | â˜ opcional | `true` para sites com preÃ§os renderizados via JavaScript |

### Como descobrir o seletor CSS correto

1. Abra a pÃ¡gina do produto no navegador
2. Clique com o botÃ£o direito no preÃ§o â†’ **"Inspecionar"**
3. Identifique a classe ou ID do elemento HTML que contÃ©m o preÃ§o
4. Adicione-o Ã  lista `price_selectors`

**Exemplos por loja:**

> â„¹ï¸ Para **Kabum, Pichau, Amazon e Terabyte** o bot jÃ¡ possui scrapers dedicados â€” os seletores abaixo sÃ£o complemento opcional:

| Loja | Seletores comuns (se precisar personalizar) |
|------|---------------------------------------------|
| Kabum | `h4.finalPrice`, `.priceCard`, `[data-testid='new-price']` |
| Pichau | `.MuiTypography-h1`, `[class*='price']`, `.productPrice` |
| Terabyte | `.prod-new-price span`, `#prod-new-price`, `.val_principal` |
| Amazon | `.a-price-whole`, `.a-offscreen`, `[class*='apexPriceToPay']` |
| Americanas | `.priceSales`, `[class*='price']` |
| Mercado Livre | `.andes-money-amount__fraction`, `[class*='price-tag']` |

---

## ðŸ“Š Estrutura da Planilha

| Coluna | Exemplo | DescriÃ§Ã£o |
|--------|---------|-----------|
| `data` | 2026-03-09 | Data da verificaÃ§Ã£o |
| `produto` | RTX 4070 Super | Nome do produto |
| `loja` | Kabum | Loja detectada automaticamente |
| `preco` | 3499.90 | PreÃ§o atual |
| `url` | https://... | URL do produto |
| `preco_minimo_historico` | 3299.00 | Menor preÃ§o jÃ¡ registrado |

---

## â–¶ï¸ ExecuÃ§Ã£o sem GUI

```bash
# Com ambiente virtual ativo
python main.py
```

**Exemplo de saÃ­da:**

```
2026-03-09 14:35:52 [INFO ] main: [1/11] Verificando: RTX 4070 Super (Kabum)
2026-03-09 14:35:55 [INFO ] main:   â†’ MÃ©todo: jsonld | ConfianÃ§a: 98%
2026-03-09 14:35:56 [INFO ] sheets: Linha adicionada: [RTX 4070 Super] R$ 3.499,90 em 2026-03-09
2026-03-09 14:36:07 [INFO ] main: =================================================================
2026-03-09 14:36:07 [INFO ] main:   RESUMO DA EXECUÃ‡ÃƒO
2026-03-09 14:36:07 [INFO ] main:   âœ“ Registrados com sucesso : 9
2026-03-09 14:36:07 [INFO ] main:   â†’ Pulados (jÃ¡ registrados): 0
2026-03-09 14:36:07 [INFO ] main:   âœ— Erros                   : 0
```

---

## ðŸ”” ConfiguraÃ§Ã£o do Telegram (Opcional)

### 1. Criar o bot

1. Inicie conversa com **@BotFather** no Telegram
2. Envie `/newbot` e siga as instruÃ§Ãµes â†’ copie o **token**

### 2. Obter o Chat ID

1. Envie qualquer mensagem para o bot
2. Acesse: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
3. Copie o `"id"` dentro de `"chat"`

### 3. Ativar no app

Configure na aba âš™ï¸ ConfiguraÃ§Ãµes ou diretamente no `config.json`:

```json
"telegram": {
  "enabled": true,
  "bot_token": "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
  "chat_id": "987654321",
  "alert_on_new_low": true
}
```

Quando ativado, vocÃª receberÃ¡:

```
ðŸ”¥ NOVO MÃNIMO HISTÃ“RICO!

ðŸ“¦ Produto: RTX 4070 Super
ðŸª Loja: Kabum
ðŸ’° PreÃ§o atual: R$ 3.299,90
ðŸ“‰ MÃ­nimo anterior: R$ 3.499,90
ðŸ’¸ Economia: R$ 200,00
ðŸ”— Ver produto
```

---

## â° AutomaÃ§Ã£o

### Windows â€” Agendador de Tarefas

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **"Criar Tarefa BÃ¡sica"**
3. Nome: `Price Checker Bot` â€” Gatilho: **Diariamente** Ã s **08:00**
4. AÃ§Ã£o: **Iniciar um programa**
   - Programa: `C:\caminho\para\PriceCheckerBot\PriceCheckerBot.exe`
   - Iniciar em: `C:\caminho\para\PriceCheckerBot\`

### Linux / macOS â€” Cron (modo desenvolvimento)

Execute `crontab -e` e adicione:

```cron
0 8 * * * /caminho/para/venv/bin/python /caminho/para/price-checker-bot/main.py >> /caminho/para/logs/cron.log 2>&1
```

### GitHub Actions â€” Na nuvem (grÃ¡tis)

Crie `.github/workflows/price-checker.yml`:

```yaml
name: Price Checker Bot

on:
  schedule:
    - cron: "0 11 * * *"   # 08:00 horÃ¡rio de BrasÃ­lia
  workflow_dispatch:

jobs:
  run-bot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: playwright install chromium
      - name: Criar credentials.json
        run: echo '${{ secrets.GOOGLE_CREDENTIALS }}' > credentials.json
      - run: python main.py
        env:
          PYTHONIOENCODING: utf-8
```

**Configurar secret:** Settings â†’ Secrets and Variables â†’ Actions â†’ `GOOGLE_CREDENTIALS` â†’ cole o conteÃºdo do `credentials.json`.

> âš ï¸ Nunca use em repositÃ³rios pÃºblicos sem proteger as credenciais via secrets.

---

## ðŸ“‹ Logs

Gravados em `logs/price_tracker.log` e exibidos na aba Monitoramento do app.

Formato:
```
2026-03-09 14:35:52 [INFO ] main: mensagem
```

Para ativar logs mais detalhados, altere em `main.py`:
```python
setup_logging(level="DEBUG")
```

---

## ðŸ› ï¸ SoluÃ§Ã£o de Problemas

### âŒ "Planilha nÃ£o encontrada"
- O nome em `spreadsheet_name` deve ser **idÃªntico** ao nome no Google Drive (incluindo maiÃºsculas)
- Confirme que a planilha foi compartilhada com o `client_email` do `credentials.json`

### âŒ "credentials.json nÃ£o encontrado"
- O arquivo deve estar na mesma pasta do `PriceCheckerBot.exe` (ou do `main.py` em modo dev)

### âŒ PreÃ§o nÃ£o extraÃ­do / mÃ©todo: heurÃ­stica
- O site pode ter atualizado o HTML â€” inspecione e atualize os seletores em `price_selectors`
- Se o preÃ§o Ã© renderizado por JavaScript, ative `use_playwright: true` na aba Produtos

### âŒ Playwright â€” browser nÃ£o encontrado
- O build copia o Chromium automaticamente de `%LOCALAPPDATA%\ms-playwright\`
- Se essa pasta estiver vazia: execute `playwright install chromium` (ou `venv\Scripts\playwright install chromium`) e refaÃ§a o build com `.\build.bat`

### âŒ Erro de autenticaÃ§Ã£o no Google
- Verifique se as APIs **Google Sheets** e **Google Drive** estÃ£o ativadas no projeto
- Confirme que o `credentials.json` Ã© da **service account** (nÃ£o OAuth 2.0)

### âŒ Bot Telegram nÃ£o envia mensagens
- Verifique `enabled: true` e os valores de `bot_token` e `chat_id`
- Certifique-se de ter iniciado uma conversa com o bot antes de receber mensagens

### âŒ Interface grÃ¡fica nÃ£o abre
- Execute: `python -c "import tkinter; tkinter.Tk().destroy(); print('OK')"`
- No Linux: `sudo apt install python3-tk`
- No `.exe`: verifique se `_internal\_tcl_data` e `_internal\_tk_data` existem na pasta

---

## ðŸ“œ LicenÃ§a

MIT License â€” sinta-se livre para usar, modificar e distribuir.

