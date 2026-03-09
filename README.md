# 🤖 Price Checker Bot

Bot em Python que monitora preços de peças de hardware em lojas brasileiras e registra o histórico em uma planilha do Google Sheets, com suporte a alertas via Telegram.

---

## 📁 Estrutura do Projeto

```
price-checker-bot/
│
├── main.py           # Orquestrador principal — ponto de entrada
├── scraper.py        # Extração de preços via BeautifulSoup
├── sheets.py         # Integração com Google Sheets
├── notifier.py       # Alertas via Telegram (opcional)
├── config_gui.py     # Interface gráfica para configurar o bot (Tkinter)
├── config.json       # Configuração de produtos e credenciais
├── requirements.txt  # Dependências Python
├── .gitignore        # Arquivos ignorados pelo Git
├── credentials.json  # ⚠️ NÃO versionar — credenciais do Google
└── logs/
    └── price_tracker.log  # Logs gerados automaticamente
```

---

## ⚙️ Pré-requisitos

- Python 3.10 ou superior
- Conta Google com acesso ao Google Cloud Console
- Conta Telegram com bot criado (opcional, para alertas)

---

## 🚀 Instalação

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

---

## 🔑 Configuração do Google Sheets

### Passo 1 — Criar projeto no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Clique em **"Novo Projeto"** e dê um nome (ex: `price-checker-bot`)
3. Com o projeto selecionado, vá em **APIs e Serviços → Biblioteca**
4. Ative as APIs:
   - **Google Sheets API**
   - **Google Drive API**

### Passo 2 — Criar Service Account

1. Vá em **APIs e Serviços → Credenciais**
2. Clique em **"Criar Credenciais" → "Conta de Serviço"**
3. Preencha o nome (ex: `price-bot`) e clique em **"Criar e Continuar"**
4. Clique em **"Concluir"** (sem atribuir funções é suficiente)
5. Na lista, clique na service account criada
6. Vá na aba **"Chaves" → "Adicionar Chave" → "Criar nova chave"**
7. Escolha formato **JSON** e clique em **"Criar"**
8. O arquivo `credentials.json` será baixado automaticamente
9. **Mova-o para a pasta raiz do projeto** (onde está o `main.py`)

> ⚠️ **Nunca suba o `credentials.json` para repositórios públicos!**

### Passo 3 — Criar e compartilhar a planilha

1. Acesse [sheets.google.com](https://sheets.google.com) e crie uma planilha
2. Nomeie-a exatamente como definido em `config.json` (padrão: `Price Tracker`)
3. Abra o `credentials.json` e copie o valor de `client_email`
4. Na planilha, clique em **Compartilhar** e cole o e-mail da service account
5. Conceda permissão de **Editor** e salve

> O bot criará automaticamente o cabeçalho na primeira execução.

---

## �️ Interface Gráfica de Configuração

Para facilitar a configuração do bot sem editar o `config.json` diretamente, utilize a interface gráfica:

```bash
python config_gui.py
```

> Usa apenas **Tkinter**, que já vem embutido no Python — nenhuma dependência extra necessária.

### Aba ⚙️ Configurações Gerais

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
| **➕ Adicionar** | Abre formulário para novo produto |
| **✏️ Editar** | Edita o produto selecionado (duplo clique também funciona) |
| **🗑️ Remover** | Remove com confirmação |
| **⬆ / ⬇ Reordenar** | Muda a ordem de verificação dos produtos |

No formulário de produto, os **seletores CSS** são inseridos um por linha, do mais específico para o mais genérico. O bot tentará cada um em sequência até encontrar o preço.

### Salvando

Clique em **"Salvar configurações"** — o `config.json` é atualizado imediatamente. O bot utilizará as novas configurações na próxima execução.

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
      "store": "Kabum",
      "url": "https://www.kabum.com.br/produto/XXXXX/nome-do-produto",
      "price_selectors": [
        "h4.finalPrice",
        ".priceCard",
        "[data-testid='new-price']"
      ]
    }
  ]
}
```

### Campos do produto

| Campo             | Obrigatório | Descrição                                                  |
|-------------------|-------------|-------------------------------------------------------------|
| `name`            | ✅          | Nome do produto (usado como identificador único)            |
| `store`           | ✅          | Nome da loja                                               |
| `url`             | ✅          | URL completa da página do produto                          |
| `price_selectors` | ✅          | Lista de seletores CSS, tentados em ordem até o primeiro sucesso |

### Como descobrir o seletor CSS correto

1. Abra a página do produto no navegador
2. Clique com o botão direito no preço → **"Inspecionar"**
3. Identifique a classe ou ID do elemento HTML que contém o preço
4. Adicione-o à lista `price_selectors`

**Exemplos por loja:**

| Loja      | Seletores comuns                                              |
|-----------|---------------------------------------------------------------|
| Kabum     | `h4.finalPrice`, `.priceCard`, `[data-testid='new-price']`   |
| Pichau    | `.MuiTypography-h1`, `[class*='price']`, `.productPrice`     |
| Terabyte  | `.prod-new-price span`, `#prod-new-price`, `.val_principal`  |
| Americanas| `.priceSales`, `[class*='price']`                            |
| Mercado Livre | `.andes-money-amount__fraction`, `[class*='price-tag']`  |

---

## 📊 Estrutura da Planilha

O bot preenche automaticamente as seguintes colunas:

| Coluna                  | Exemplo                     | Descrição                          |
|-------------------------|-----------------------------|------------------------------------|
| `data`                  | 2026-03-08                  | Data da verificação                |
| `produto`               | RTX 4070 Super              | Nome do produto                    |
| `loja`                  | Kabum                       | Nome da loja                       |
| `preco`                 | 3499.90                     | Preço atual                        |
| `url`                   | https://kabum.com.br/...    | URL do produto                     |
| `preco_minimo_historico`| 3299.00                     | Menor preço já registrado          |

---

## ▶️ Execução Manual

```bash
# Com ambiente virtual ativo
python main.py
```

**Exemplo de saída:**

```
2026-03-08 10:00:00 [INFO    ] __main__: =================================================================
2026-03-08 10:00:00 [INFO    ] __main__:   PRICE CHECKER BOT — Iniciando execução
2026-03-08 10:00:00 [INFO    ] __main__:   Data: 2026-03-08
2026-03-08 10:00:00 [INFO    ] __main__:   Conectando ao Google Sheets...
2026-03-08 10:00:02 [INFO    ] sheets: Conectado à planilha 'Price Tracker' com sucesso.
2026-03-08 10:00:02 [INFO    ] __main__: [1/3] Verificando: RTX 4070 Super (Kabum)
2026-03-08 10:00:05 [INFO    ] scraper: ✓ Preço extraído com seletor 'h4.finalPrice': R$ 3.499,90
2026-03-08 10:00:06 [INFO    ] sheets: Linha adicionada: [RTX 4070 Super] R$ 3.499,90 em 2026-03-08
2026-03-08 10:00:06 [INFO    ] __main__:   RESUMO: ✓ 3 registrados | → 0 pulados | ✗ 0 erros
```

---

## 🔔 Configuração do Telegram (Opcional)

### 1. Criar o bot

1. Abra o Telegram e inicie conversa com **@BotFather**
2. Envie `/newbot` e siga as instruções
3. Copie o **token** fornecido

### 2. Obter o Chat ID

1. Inicie uma conversa com seu bot (envie qualquer mensagem)
2. Acesse no navegador:
   ```
   https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
   ```
3. Copie o valor de `"id"` dentro de `"chat"`

### 3. Configurar no `config.json`

```json
"telegram": {
  "enabled": true,
  "bot_token": "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
  "chat_id": "987654321",
  "alert_on_new_low": true
}
```

Quando ativado, você receberá mensagens como:

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

### Linux / macOS — Cron

Execute `crontab -e` e adicione a linha abaixo para rodar todo dia às 08:00:

```cron
0 8 * * * /caminho/para/venv/bin/python /caminho/para/price-checker-bot/main.py >> /caminho/para/price-checker-bot/logs/cron.log 2>&1
```

Para descobrir o caminho do Python no venv:
```bash
which python  # (com venv ativado)
```

---

### Windows — Agendador de Tarefas (Task Scheduler)

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **"Criar Tarefa Básica"**
3. Nome: `Price Checker Bot`
4. Gatilho: **Diariamente** às **08:00**
5. Ação: **Iniciar um programa**
   - Programa: `C:\caminho\para\venv\Scripts\python.exe`
   - Argumentos: `C:\caminho\para\price-checker-bot\main.py`
   - Iniciar em: `C:\caminho\para\price-checker-bot\`
6. Marque **"Executar estando o usuário conectado ou não"**

---

### GitHub Actions — Execução na nuvem (grátis)

Crie o arquivo `.github/workflows/price-checker.yml`:

```yaml
name: Price Checker Bot

on:
  schedule:
    # Roda todo dia às 11:00 UTC (08:00 no horário de Brasília)
    - cron: "0 11 * * *"
  workflow_dispatch:   # Permite execução manual pelo GitHub

jobs:
  run-bot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout do repositório
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Instalar dependências
        run: pip install -r requirements.txt

      - name: Criar credentials.json a partir do secret
        run: echo '${{ secrets.GOOGLE_CREDENTIALS }}' > credentials.json

      - name: Executar o bot
        run: python main.py
        env:
          PYTHONIOENCODING: utf-8
```

**Configurar o secret no GitHub:**
1. Vá em **Settings → Secrets and Variables → Actions**
2. Clique em **"New repository secret"**
3. Nome: `GOOGLE_CREDENTIALS`
4. Valor: cole todo o conteúdo do seu `credentials.json`

> ⚠️ **Nunca use o GitHub Actions em repositórios públicos** sem proteger as credenciais via secrets.

---

## 📋 Logs

Os logs são gravados em `logs/price_tracker.log` e também exibidos no console.

Formato:
```
2026-03-08 10:00:00 [INFO    ] __main__: mensagem
```

Níveis de log disponíveis: `DEBUG`, `INFO`, `WARNING`, `ERROR`

Para ativar logs mais detalhados, altere a chamada em `main.py`:
```python
setup_logging(level="DEBUG")
```

---

## 🛠️ Solução de Problemas

### ❌ "Planilha não encontrada"
- Verifique se o nome em `config.json → google_sheets.spreadsheet_name` é **idêntico** ao nome da planilha no Google Drive (incluindo maiúsculas/minúsculas)
- Confirme que a planilha foi compartilhada com o e-mail da service account (`client_email` no `credentials.json`)

### ❌ "Arquivo credentials.json não encontrado"
- O arquivo deve estar na pasta raiz do projeto (mesma pasta do `main.py`)
- Verifique o caminho em `config.json → google_sheets.credentials_file`

### ❌ "Nenhum seletor funcionou para a URL"
- O site pode ter atualizado o HTML. Inspecione a página novamente no navegador e atualize os seletores em `config.json`
- Alguns sites bloqueiam scrapers. Tente adicionar cabeçalhos diferentes ou use Selenium (descomente no `requirements.txt`)
- Verifique se a URL do produto ainda é válida

### ❌ Preço None / extraído incorretamente
- Adicione o seletor correto à lista `price_selectors`
- Liste seletores do mais específico para o mais genérico
- Inspecione o HTML do elemento para garantir que o texto contém o preço completo

### ❌ Erro de autenticação no Google
- Verifique se as APIs **Google Sheets** e **Google Drive** estão ativadas no projeto do Google Cloud
- Confirme que o `credentials.json` é da service account (não OAuth 2.0 do usuário)

### ❌ Bot Telegram não envia mensagens
- Confirme que `enabled: true` está no `config.json`
- Verifique se o `bot_token` e `chat_id` estão corretos
- Certifique-se de ter iniciado uma conversa com o bot antes de tentar receber mensagens

### ❌ A interface gráfica não abre
- Verifique se o Python foi instalado com suporte a Tkinter (a instalação padrão do python.org no Windows já inclui)
- Teste com: `python -c "import tkinter; tkinter.Tk().destroy(); print('OK')"`
- No Linux, instale com: `sudo apt install python3-tk`

### ❌ Preços de páginas com JavaScript não são extraídos
- Sites como Americanas e Mercado Livre podem usar JavaScript para renderizar preços
- Instale o Selenium: descomente as linhas no `requirements.txt` e execute `pip install -r requirements.txt`
- Implemente uma versão com `webdriver` em `scraper.py` para essas URLs específicas

---

## ➕ Adicionando Novas Lojas

Basta adicionar um novo produto ao `config.json` com os seletores corretos:

```json
{
  "name": "Nome do Produto",
  "store": "Nome da Loja",
  "url": "https://www.loja.com.br/produto/xxxxx",
  "price_selectors": [
    ".seletor-css-principal",
    ".seletor-css-alternativo"
  ]
}
```

---

## 📜 Licença

MIT License — sinta-se livre para usar, modificar e distribuir.
