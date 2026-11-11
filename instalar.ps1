# Fatura OCR - instalador para Windows.
#
# Jeito facil: clique duas vezes em "instalar.cmd".
# Sem baixar nada antes: abra o PowerShell e cole
#   [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/lucasns97/ocr-fatura/main/instalar.ps1 | iex
# (a primeira parte liga o TLS 1.2; sem ela o PowerShell 5 do Windows pode falhar com
#  "A conexao subjacente estava fechada")
#
# O que ele faz:
#   1. instala o uv (gerenciador de Python da Astral), se ainda nao tiver;
#   2. copia o programa para %LOCALAPPDATA%\FaturaOCR (baixa do GitHub se preciso);
#   3. instala o Python e as dependencias (o uv cuida disso, sem mexer no resto do sistema);
#   4. cria o atalho "Fatura OCR" na Area de Trabalho e no Menu Iniciar.
# Rodar de novo atualiza o programa. Seus dados (nomes de estabelecimentos) ficam em
# %USERPROFILE%\.fatura-ocr e nao sao apagados.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # deixa os downloads bem mais rapidos no PowerShell 5
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo = 'lucasns97/ocr-fatura'
$Dest = Join-Path $env:LOCALAPPDATA 'FaturaOCR'

function Step($msg) { Write-Host ''; Write-Host "==> $msg" -ForegroundColor Cyan }

function Install-FaturaOcr {
    # 1. uv
    Step 'Verificando o uv (gerenciador de Python)'
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host 'Instalando o uv (https://docs.astral.sh/uv/)...'
        # processo novo: liga o TLS 1.2 nele tambem (nao herda a configuracao deste)
        powershell -NoProfile -ExecutionPolicy Bypass -Command '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://astral.sh/uv/install.ps1 | iex'
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw 'Nao foi possivel instalar o uv. Verifique a internet e rode o instalador de novo.'
        }
    }
    Write-Host ('uv encontrado: ' + (Get-Command uv).Source)

    # 2. arquivos do programa
    Step "Copiando o programa para $Dest"
    $running = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dest\*" }
    if ($running) { throw 'O Fatura OCR esta aberto. Feche a janela dele e rode o instalador de novo.' }
    $src = $PSScriptRoot
    $tmp = $null
    $ver = $null
    # Rodando da pasta ja instalada (ou sem pasta, via "irm | iex"): baixa a versao mais recente.
    $isInstalled = $src -and ((Resolve-Path $src).Path.TrimEnd('\') -eq $Dest.TrimEnd('\'))
    if (-not $src -or $isInstalled -or -not (Test-Path (Join-Path $src 'pyproject.toml'))) {
        Write-Host "Baixando a versao mais recente de github.com/$Repo ..."
        $tmp = Join-Path $env:TEMP ('fatura-ocr-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        $zip = Join-Path $tmp 'app.zip'
        # a versao mais recente publicada (o CI publica uma a cada mudanca aprovada); o atalho compara
        # com ela para oferecer atualizacao. Sem versao publicada (ou sem acesso a API), baixa o main.
        try { $ver = (Invoke-RestMethod -UseBasicParsing -TimeoutSec 20 -Uri "https://api.github.com/repos/$Repo/releases/latest").tag_name } catch { $ver = $null }
        $ref = if ($ver) { "refs/tags/$ver" } else { 'refs/heads/main' }
        if ($ver) { Write-Host "Versao $ver" }
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/$ref.zip" -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $src = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
    }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    # troca os arquivos do programa; mantem o .venv para a atualizacao ser rapida
    Get-ChildItem $Dest -Force | Where-Object { $_.Name -ne '.venv' } | Remove-Item -Recurse -Force
    Get-ChildItem $src -Force | Where-Object { $_.Name -notin @('.git', '.venv') } |
        Copy-Item -Destination $Dest -Recurse -Force
    if ($tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    # versao instalada (so quando baixada do GitHub; instalando de uma copia local, fica desconhecida)
    if ($ver) { Set-Content -Path (Join-Path $Dest 'VERSION') -Value $ver -Encoding Ascii }

    # 3. Python + dependencias
    Step 'Instalando o Python e as dependencias (a primeira vez leva alguns minutos)'
    Push-Location $Dest
    try {
        & uv sync --frozen --no-dev
        if ($LASTEXITCODE -ne 0) { throw "uv sync falhou (codigo $LASTEXITCODE)." }
    } finally { Pop-Location }

    # 4. atalhos
    Step 'Criando os atalhos'
    # O Windows guarda o icone em cache pelo caminho do arquivo: com o mesmo caminho, um icone novo
    # continuava aparecendo o antigo (mesmo apagando o atalho). O nome leva um pedaco do hash do
    # conteudo, entao um icone novo tem um caminho novo.
    $ico = Join-Path $Dest 'assets\fatura.ico'
    # (se o hash ou a copia falhar, usa o caminho fixo: um icone velho nao deve impedir a instalacao)
    $icoLnk = $ico
    try {
        $icoTag = (Get-FileHash -Algorithm SHA256 -Path $ico).Hash.Substring(0, 8).ToLower()
        $icoLnk = Join-Path $Dest "assets\fatura-$icoTag.ico"
        Copy-Item -Path $ico -Destination $icoLnk -Force
    } catch { $icoLnk = $ico }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
        if (-not $dir) { continue }
        $lnk = $shell.CreateShortcut((Join-Path $dir 'Fatura OCR.lnk'))
        $lnk.TargetPath = Join-Path $Dest 'iniciar.cmd'
        $lnk.WorkingDirectory = $Dest
        $lnk.IconLocation = $icoLnk + ',0'
        $lnk.Description = 'Fatura OCR: capturas da fatura para CSV'
        $lnk.Save()
        Write-Host "Atalho criado em $dir"
    }
    # pede ao Windows para redesenhar os icones (Windows 10/11); se nao existir, o icone novo aparece depois
    $ie4 = Join-Path $env:SystemRoot 'System32\ie4uinit.exe'
    if (Test-Path $ie4) { try { & $ie4 -show; $global:LASTEXITCODE = 0 } catch { } }

    Write-Host ''
    Write-Host 'Pronto! Para abrir, use o atalho "Fatura OCR" na Area de Trabalho ou no Menu Iniciar.' -ForegroundColor Green
    if ($env:CI) { return }   # CI (GitHub Actions): sem pergunta
    if ($env:FATURA_OCR_UPDATING) { return }   # atualizacao pedida pelo atalho: ele mesmo abre a versao nova
    $answer = Read-Host 'Abrir o Fatura OCR agora? [S/n]'
    if ($answer -notmatch '^[nN]') { Start-Process -FilePath (Join-Path $Dest 'iniciar.cmd') }
}

try {
    Install-FaturaOcr
} catch {
    # sem "exit": quem colou o comando no PowerShell nao perde a janela
    Write-Host ''
    Write-Host ('ERRO: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'A instalacao nao terminou. Corrija o problema acima e rode o instalador de novo.'
    Write-Host '(Os nomes de estabelecimentos salvos em %USERPROFILE%\.fatura-ocr nao foram tocados.)'
    if ($env:CI) { throw }   # so no CI: falha o job em vez de terminar com sucesso
}
