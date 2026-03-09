# 🤖 Price Checker Bot

Bot em Python que monitora preços de produtos em lojas brasileiras e registra o histórico em uma planilha do Google Sheets, com alertas via Telegram e interface gráfica completa.

---

## 📁 Estrutura do Projeto

```
price-checker-bot/
│
├── app.py               # Interface gráfica principal (launcher + configurações)
├── main.py              # Orquestrador principal — pode ser chamado diretamente
├── config_gui.py        # Editor de configuração standalone (legado / opcional)
├── sheets.py            # Integração com Google Sheets
├── notifier.py          # Alertas via Telegram (opcional)
├── config.json          # Configuração de produtos e credenciais
├── credentials.json     # ⚠️ NÃO versionar — credenciais do Google
├── requirements.txt     # Dependências Python
├── build.py             # Script de empacotamento para .exe (PyInstaller)
├── build.bat            # Atalho: chama venv\Scripts\python.exe build.py
│
├── price_tracker/       # Pacote principal de extração de preços
│   ├── core/
│   │   ├── price_extractor.py   # Orquestrador das 4 camadas
│   │   ├── jsonld_parser.py     # Camada 1 — JSON-LD (dados estruturados)
│   │   ├── store_detector.py    # Detecta a loja pela URL
│   │   └── heuristics.py        # Camada 4 — heurística por pontuação
│   ├── scrapers/
│   │   ├── kabum.py             # Scraper dedicado Kabum
│   │   ├── pichau.py            # Scraper dedicado Pichau
│   │   ├── amazon.py            # Scraper dedicado Amazon
│   │   └── terabyte.py          # Scraper dedicado Terabyte
│   └── utils/
│       ├── html_fetcher.py      # HTTP com cache, retry, cloudscraper e Playwright
│       └── price_parser.py      # Normalização (R$ 3.499,90 → 3499.90)
│
├── tests/               # Testes unitários (pytest)
└── logs/
    └── price_tracker.log
```

---

## 🖥️ Interface Gráfica (app.py)

O `app.py` é o ponto de entrada principal. Reúne em uma única janela:

| Aba | Função |
|-----|--------|
| **▶ Monitoramento** | Botão de execução, barra de progresso e log em tempo real |
| **⚙️ Configurações** | Google Sheets, Telegram e opções gerais |
| **📦 Produtos** | Adicionar, editar, remover e reordenar produtos monitorados |
| **🏪 Lojas** | Gerenciar o mapeamento domínio → scraper dedicado |

Para iniciar:

```bash
python app.py
```

### Aba ▶ Monitoramento

- Clique em **▶ Iniciar** para disparar a verificação de todos os produtos.
- A barra de progresso mostra `[produto atual / total]`.
- O log exibe INFO, DEBUG, WARNING e ERROR com cores distintas.
- O bot roda em thread separada — a interface não trava durante a execução.

### Aba ⚙️ Configurações

| Campo | Descrição |
|---|---|
| Arquivo de credenciais | Caminho para o `credentials.json` do Google |
| Nome da planilha | Nome exato da planilha no Google Drive |
| Ativar Telegram | Liga/desliga os alertas |
| Bot Token | Token fornecido pelo @BotFather |
| Chat ID | ID do chat para receber os alertas |
| Alertar em novo mínimo | Envia mensagem quando o preço bate recorde |

### Aba 📦 Produtos

| Ação | Como usar |
|---|---|
| **➕ Adicionar** | Abre formulário para cadastro de novo produto |
| **✏️ Editar** | Edita o produto selecionado (duplo clique também funciona) |
| **🗑️ Remover** | Remove com confirmação |
| **⬆ / ⬇ Reordenar** | Muda a ordem de verificação |

Os **seletores CSS** são opcionais — o bot tenta JSON-LD, scraper dedicado e heurística automática antes de depender deles. O campo **`use_playwright`** ativa o browser headless para páginas com preços renderizados via JavaScript.

### Aba 🏪 Lojas

Gerencia o `STORE_MAP` em `price_tracker/core/store_detector.py`.

| Ação | Como usar |
|---|---|
| **➕ Adicionar** | Informa domínio (ex: `americanas`) e ID do scraper |
| **🗑️ Remover** | Remove domínios personalizados (builtins são protegidos) |
| **📄 Criar / Abrir Template** | Cria `price_tracker/scrapers/<id>.py` com estrutura pronta |

**Fluxo para adicionar uma nova loja:**
1. Clique em **➕ Adicionar** na aba Lojas
2. Informe o fragmento do domínio (ex: `americanas`)
3. Deixe "Criar arquivo de scraper template" marcado e clique em **Adicionar**
4. Preencha os seletores no arquivo gerado
5. Clique em **Salvar configurações** — o `store_detector.py` é atualizado

### Rodapé — Salvar / Recarregar

Visível nas abas Configurações, Produtos e Lojas:
- **Salvar configurações** — grava `config.json` e `store_detector.py`
- **Recarregar arquivo** — descarta alterações e relê o arquivo do disco

---

## ⚙️ Pré-requisitos (desenvolvimento)

- Python 3.10 ou superior
- Conta Google com acesso ao Google Cloud Console
- Conta Telegram com bot criado (opcional, para alertas)

---

## 🚀 Instalação (modo desenvolvimento)

### 1. Clone o repositório

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

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Instale o browser do Playwright

```bash
playwright install chromium
```

---

## 📦 Distribuição como .exe (Windows)

O projeto inclui um script de build que empacota tudo em `dist\PriceCheckerBot\` — incluindo o Chromium. Não é necessário instalar Python ou dependências na máquina de destino.

### Pré-requisitos do build

1. Ambiente virtual configurado com todas as dependências instaladas
2. Chromium instalado: `venv\Scripts\playwright install chromium`

### Gerar o .exe

```bat
.\build.bat
```

O que o `build.py` faz:
1. Instala/atualiza o PyInstaller
2. Detecta e inclui os binários do Tcl/Tk automaticamente
3. Roda o PyInstaller com `--onedir` e todos os `--collect-all` necessários
4. Copia o Chromium de `%LOCALAPPDATA%\ms-playwright\` para dentro do bundle
5. Copia `config.json`, `credentials.json` e `icon.ico` para a pasta de saída

**Saída:** `dist\PriceCheckerBot\PriceCheckerBot.exe`

### Distribuir

```powershell
Compress-Archive -Path "dist\PriceCheckerBot" -DestinationPath "dist\PriceCheckerBot-v1.0.0.zip"
```

O usuário final coloca o `credentials.json` dentro da pasta `PriceCheckerBot\` e executa o `.exe`. O Chromium já está embutido — nenhuma instalação adicional é necessária.

---

## 🔑 Configuração do Google Sheets

### Passo 1 — Criar projeto no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Clique em **"Novo Projeto"** e dê um nome (ex: `price-checker-bot`)
3. Em **APIs e Serviços → Biblioteca**, ative:
   - **Google Sheets API**
   - **Google Drive API**

### Passo 2 — Criar Service Account

1. Vá em **APIs e Serviços → Credenciais**
2. Clique em **"Criar Credenciais" → "Conta de Serviço"**
3. Preencha o nome (ex: `price-bot`) → **"Criar e Continuar"** → **"Concluir"**
4. Na lista, clique na service account criada
5. Vá em **"Chaves" → "Adicionar Chave" → "Criar nova chave"** → formato **JSON**
6. Mova o arquivo baixado para a pasta raiz do projeto com o nome `credentials.json`

> ⚠️ **Nunca suba o `credentials.json` para repositórios públicos!**

### Passo 3 — Criar e compartilhar a planilha

1. Acesse [sheets.google.com](https://sheets.google.com) e crie uma planilha
2. Nomeie-a exatamente como em `config.json` (`spreadsheet_name`)
3. Abra o `credentials.json`, copie o `client_email`
4. Na planilha, clique em **Compartilhar** → cole o e-mail → permissão **Editor**

> O bot cria o cabeçalho automaticamente na primeira execução.

---

## 🧱 Arquitetura de Extração de Preços

O bot usa uma **estratégia em 4 camadas**, do mais ao menos confiável:

| Camada | Método | Confiança | Descrição |
|--------|---------|-----------|-----------|
| 1 | **JSON-LD** | 98% | `<script type="application/ld+json">` — mais estável |
| 2 | **Scraper dedicado** | 88–92% | Seletores CSS por loja (Kabum, Pichau, Amazon, Terabyte) |
| 3 | **Seletores do config** | 75% | Seletores definidos manualmente no `config.json` |
| 4 | **Heurística** | 30–85% | Regex + pontuação de elementos — fallback automático |

Páginas que exigem JavaScript usam a camada extra **Playwright** (Chromium headless), ativada por `use_playwright: true` na configuração do produto.

**Para adicionar suporte a uma nova loja programaticamente:**
1. Crie `price_tracker/scrapers/<loja>.py` com `extract(soup) -> dict | None`
2. Adicione a entrada em `STORE_MAP` no `store_detector.py`

---

## 📝 Configuração Manual do `config.json`

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

| Campo | Obrigatório | Descrição |
|---|---|---|
| `name` | ✅ | Nome do produto (identificador único) |
| `url` | ✅ | URL completa da página do produto |
| `price_selectors` | opcional | Lista de seletores CSS (camada 3 — pode ser omitida) |
| `use_playwright` | opcional | `true` para sites com preços renderizados via JavaScript |

### Como descobrir o seletor CSS correto

1. Abra a página do produto no navegador
2. Clique com o botão direito no preço → **"Inspecionar"**
3. Identifique a classe ou ID do elemento HTML que contém o preço
4. Adicione-o à lista `price_selectors`

**Exemplos por loja:**

> Para **Kabum, Pichau, Amazon e Terabyte** o bot já possui scrapers dedicados — os seletores abaixo são complemento opcional:

| Loja | Seletores comuns (se precisar personalizar) |
|------|---------------------------------------------|
| Kabum | `h4.finalPrice`, `.priceCard`, `[data-testid='new-price']` |
| Pichau | `.MuiTypography-h1`, `[class*='price']`, `.productPrice` |
| Terabyte | `.prod-new-price span`, `#prod-new-price`, `.val_principal` |
| Amazon | `.a-price-whole`, `.a-offscreen`, `[class*='apexPriceToPay']` |
| Americanas | `.priceSales`, `[class*='price']` |
| Mercado Livre | `.andes-money-amount__fraction`, `[class*='price-tag']` |

---

## 📊 Estrutura da Planilha

| Coluna | Exemplo | Descrição |
|--------|---------|-----------|
| `data` | 2026-03-09 | Data da verificação |
| `produto` | RTX 4070 Super | Nome do produto |
| `loja` | Kabum | Loja detectada automaticamente |
| `preco` | 3499.90 | Preço atual |
| `url` | https://... | URL do produto |
| `preco_minimo_historico` | 3299.00 | Menor preço já registrado |

---

## ▶️ Execução sem GUI

```bash
python main.py
```

**Exemplo de saída:**

```
2026-03-09 14:35:52 [INFO ] main: [1/11] Verificando: RTX 4070 Super (Kabum)
2026-03-09 14:35:55 [INFO ] main:   → Método: jsonld | Confiança: 98%
2026-03-09 14:35:56 [INFO ] sheets: Linha adicionada: [RTX 4070 Super] R$ 3.499,90 em 2026-03-09
2026-03-09 14:36:07 [INFO ] main: =================================================================
2026-03-09 14:36:07 [INFO ] main:   RESUMO DA EXECUÇÃO
2026-03-09 14:36:07 [INFO ] main:   ✓ Registrados com sucesso : 9
2026-03-09 14:36:07 [INFO ] main:   → Pulados (já registrados): 0
2026-03-09 14:36:07 [INFO ] main:   ✗ Erros                   : 0
```

---

## 🔔 Configuração do Telegram (Opcional)

### 1. Criar o bot

1. Inicie conversa com **@BotFather** no Telegram
2. Envie `/newbot` e siga as instruções → copie o **token**

### 2. Obter o Chat ID

1. Envie qualquer mensagem para o bot
2. Acesse: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
3. Copie o `"id"` dentro de `"chat"`

### 3. Ativar

Configure na aba ⚙️ Configurações do app ou diretamente no `config.json`:

```json
"telegram": {
  "enabled": true,
  "bot_token": "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
  "chat_id": "987654321",
  "alert_on_new_low": true
}
```

Quando ativado, você receberá:

```
🔥 NOVO MÍNIMO HISTÓRICO!

📦 Produto: RTX 4070 Super
🏪 Loja: Kabum
💰 Preço atual: R$ 3.299,90
📉 Mínimo anterior: R$ 3.499,90
💸 Economia: R$ 200,00
🔗 Ver produto
```

---

## ⏰ Automação

### Windows — Agendador de Tarefas

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **"Criar Tarefa Básica"**
3. Nome: `Price Checker Bot` — Gatilho: **Diariamente** às **08:00**
4. Ação: **Iniciar um programa**
   - Programa: `C:\caminho\para\PriceCheckerBot\PriceCheckerBot.exe`
   - Iniciar em: `C:\caminho\para\PriceCheckerBot\`

### Linux / macOS — Cron (modo desenvolvimento)

```cron
0 8 * * * /caminho/para/venv/bin/python /caminho/para/price-checker-bot/main.py >> /caminho/para/logs/cron.log 2>&1
```

### GitHub Actions — Na nuvem (grátis)

Crie `.github/workflows/price-checker.yml`:

```yaml
name: Price Checker Bot

on:
  schedule:
    - cron: "0 11 * * *"   # 08:00 horário de Brasília
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

**Configurar secret:** Settings → Secrets and Variables → Actions → `GOOGLE_CREDENTIALS` → cole o conteúdo do `credentials.json`.

> ⚠️ Nunca use em repositórios públicos sem proteger as credenciais via secrets.

---

## 📋 Logs

Gravados em `logs/price_tracker.log` e exibidos na aba Monitoramento do app.

```
2026-03-09 14:35:52 [INFO ] main: mensagem
```

Para ativar logs mais detalhados, altere em `main.py`:

```python
setup_logging(level="DEBUG")
```

---

## 🛠️ Solução de Problemas

### ❌ "Planilha não encontrada"
- O nome em `spreadsheet_name` deve ser **idêntico** ao nome no Google Drive (incluindo maiúsculas)
- Confirme que a planilha foi compartilhada com o `client_email` do `credentials.json`

### ❌ "credentials.json não encontrado"
- O arquivo deve estar na mesma pasta do `PriceCheckerBot.exe` (ou do `main.py` em modo dev)

### ❌ Preço não extraído / método: heurística
- O site pode ter atualizado o HTML — inspecione e atualize os seletores em `price_selectors`
- Se o preço é renderizado por JavaScript, ative `use_playwright: true` na aba Produtos

### ❌ Playwright — browser não encontrado
- O build copia o Chromium automaticamente de `%LOCALAPPDATA%\ms-playwright\`
- Se essa pasta estiver vazia: execute `playwright install chromium` e refaça o build com `.\build.bat`

### ❌ Erro de autenticação no Google
- Verifique se as APIs **Google Sheets** e **Google Drive** estão ativadas no projeto
- Confirme que o `credentials.json` é da **service account** (não OAuth 2.0)

### ❌ Bot Telegram não envia mensagens
- Verifique `enabled: true` e os valores de `bot_token` e `chat_id`
- Certifique-se de ter iniciado uma conversa com o bot antes de receber mensagens

### ❌ Interface gráfica não abre
- Execute: `python -c "import tkinter; tkinter.Tk().destroy(); print('OK')"`
- No Linux: `sudo apt install python3-tk`
- No `.exe`: verifique se `_internal\_tcl_data` e `_internal\_tk_data` existem na pasta

---

## 📜 Licença

MIT License — sinta-se livre para usar, modificar e distribuir.

