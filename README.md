# Fatura OCR

Transforma **capturas de tela da fatura do cartão** (app do Inter) em uma **planilha CSV**, sem digitar nada.
Tudo roda **no seu computador**: as imagens não são enviadas para nenhum lugar.

O formato do CSV:

| Data | Lançamento | Categoria | Tipo | Valor |
|---|---|---|---|---|
| 23/08/2026 | STREAMING ABC SAO PAULO BRA | ENTRETENIMENTO | Compra à vista | R$ 12,34 |
| 15/06/2026 | HOTEL FICTICIO SAO PAULO BRA | VIAGEM | Parcela 3 de 6 | R$ 200,00 |
| 02/08/2026 | PAGAMENTO ON LINE | OUTROS | Compra à vista | -R$ 2.000,00 |

*(valores ilustrativos)*

O arquivo sai com o nome `fatura-inter-AAAA-MM.csv` (ex.: `fatura-inter-2026-09.csv`), pelo mês da fatura.

---

## Instalar (Windows)

Precisa de internet só na instalação. Escolha **um** dos jeitos:

**A) Colar um comando (mais rápido)**
1. Aperte a tecla Windows, digite **PowerShell** e abra.
2. Cole esta linha **inteira** e aperte Enter:
   ```powershell
   [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/lucasns97/ocr-fatura/main/instalar.ps1 | iex
   ```
   A primeira parte liga o TLS 1.2. Sem ela, o PowerShell do Windows pode falhar com
   *"A conexão subjacente estava fechada: Erro inesperado em um envio"*.

**B) Baixar e dar dois cliques**
1. Nesta página, clique em **Code → Download ZIP** e extraia o arquivo.
2. Na pasta extraída, dê dois cliques em **`instalar.cmd`**.
   Se o Windows mostrar um aviso de segurança, clique em **Mais informações → Executar assim mesmo** (ou **Executar**).

O instalador:
- instala o [uv](https://docs.astral.sh/uv/) (ele baixa o Python certo, sem mexer no resto do computador);
- copia o programa para `%LOCALAPPDATA%\FaturaOCR`;
- cria o atalho **Fatura OCR** na Área de Trabalho e no Menu Iniciar.

A primeira instalação leva alguns minutos: baixa o Python e o leitor de imagens (o programa instalado ocupa cerca de 250 MB).

## Usar

1. Abra o atalho **Fatura OCR**. Uma janela preta abre e, em seguida, o navegador.
   **Deixe a janela preta aberta** enquanto usa; feche-a para encerrar.
2. No app do Inter, abra **Faturas**, escolha o mês e tire capturas de tela rolando de cima para baixo.
   Se o celular tiver **captura longa (rolada)**, uma imagem só com a fatura inteira também serve.
   Envie o arquivo original: imagens reduzidas por aplicativo de mensagem ficam ilegíveis (o programa avisa).
   Com várias capturas, **deixe cada uma repetir um pouco o fim da anterior** (uma ou duas transações): as linhas
   repetidas são removidas, e a repetição garante que nada fique de fora entre uma captura e outra.
3. No navegador:
   1. **Dados da fatura**: confira o mês da fatura (o mês do **vencimento**). Já vem preenchido com o
      **próximo mês**, que é o da fatura em aberto; mude se estiver lendo uma fatura já fechada.
      O app mostra só "23 de ago", sem o ano; é esse mês que permite completar a data.
      Se quiser, informe o **total da fatura**: o programa confere se a soma bate.
   2. **Capturas de tela**: arraste as imagens (ou clique para escolher). Confira a ordem (de cima para baixo) e use ↑ ↓ se precisar.
   3. Clique em **Ler capturas** (cerca de 1 segundo por imagem).
4. Depois da leitura, as seções 1 e 2 se recolhem (clique no título para abrir de novo). Confira a **Tabela**. Linhas marcadas com **revisar** tiveram leitura incerta.
   Para corrigir, edite as células e clique em **Salvar alterações**. Aparece o aviso
   **"Editado manualmente"**, e **Voltar à leitura automática** desfaz tudo.
   Nomes de estabelecimentos corrigidos são lembrados nas próximas faturas (dá para desligar).
5. Ainda na **Tabela**:
   - **Copiar para planilha**: no Google Sheets ou no Excel, clique em uma célula e cole (Ctrl+V); cada coluna vai
     para o lugar certo. O **Valor vai como número** (ex.: `1896,14`; pagamentos ficam negativos), então a
     planilha soma. Para ver como dinheiro: no Google Sheets, Formatar → Número → Moeda; no Excel, Página
     Inicial → Formato de Número → Moeda. Isso vale para planilha em português: se a sua estiver em inglês, o
     valor pode virar texto (no Google Sheets, mude em Arquivo → Configurações → Localidade: Brasil).
   - **Salvar CSV**: no Chrome e no Edge abre a janela "Salvar como" do Windows, já com o nome
     `fatura-inter-AAAA-MM.csv`, para você escolher a pasta. Em outros navegadores, o arquivo é baixado como um download comum (normalmente na pasta Downloads).
6. A aba **Resumo** mostra o total, o gasto por categoria, os maiores estabelecimentos, à vista × parcelado e as compras por mês.

## Atualizar e desinstalar

- **Atualizar:** rode o instalador de novo (o comando do item A, ou `instalar.cmd` na pasta do programa). Feche o Fatura OCR antes.
- **Desinstalar:** dois cliques em `desinstalar.cmd` (na pasta `%LOCALAPPDATA%\FaturaOCR`). Os nomes corrigidos ficam em
  `%USERPROFILE%\.fatura-ocr`; apague essa pasta se quiser removê-los também.
  O uv e o Python que ele baixou continuam no computador; para removê-los, rode no PowerShell
  `uv python uninstall --all`, depois `uv cache clean`, e apague `%USERPROFILE%\.local\bin\uv.exe`.

## O que esperar (limitações)

- Feito para a tela **Faturas do app Inter, em português**. Outros apps ou layouts provavelmente não vão funcionar.
- O texto vem do OCR: pode juntar palavras (`LOJAEXEMPLO`) ou trocar uma letra. Valores e datas são conferidos por regras
  (e pelo total, se você informar), mas **confira a tabela antes de usar**.
- O mesmo estabelecimento sai sempre com o mesmo nome: a primeira grafia lida (ou a que você corrigir) passa a valer
  para as próximas vezes.
- A data é a que o app mostra. Em casos raros ela difere da fatura em PDF (ex.: compra listada em 31/07 no app e em 01/08 no PDF).
- O ano é deduzido: a compra não pode ser depois do fechamento da fatura (por padrão, o último dia do mês anterior ao
  vencimento; dá para mudar em **Avançado**). Em parcelas, o número da parcela ajuda a achar o ano da compra original.
- Pagamentos de fatura e estornos (valores com **+** no app) saem **negativos**; compras saem positivas.

## Em outros sistemas (macOS / Linux)

Com o [uv](https://docs.astral.sh/uv/) instalado:

```bash
git clone https://github.com/lucasns97/ocr-fatura && cd ocr-fatura && uv run fatura
```

## Desenvolvimento

```bash
uv sync                      # Python 3.12 + dependências em .venv
uv run fatura --no-browser   # servidor em http://127.0.0.1:8765
./scripts/verify.sh          # todos os testes (inclui OCR real em capturas sintéticas)
```

O código fica em `src/fatura_ocr/`: `parser.py` lê o layout do app, `pipeline.py` junta as capturas e remove a
sobreposição, `server.py` é a API local e `static/` é a interface (sem bibliotecas externas). Os testes usam apenas
dados sintéticos. **Nunca adicione capturas, faturas ou CSVs reais ao repositório:** ele é público.
