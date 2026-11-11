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

# Visual do terminal (ui.ps1: logo, passos animados, barra de download). Fica ao lado deste arquivo; via
# "irm | iex" vem do GitHub. Se nao der, linhas simples: a instalacao nao depende disso.
$uiOk = $false
try {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'ui.ps1'))) { . (Join-Path $PSScriptRoot 'ui.ps1') }
    else { . ([scriptblock]::Create((Invoke-RestMethod -UseBasicParsing -TimeoutSec 15 -Uri "https://raw.githubusercontent.com/$Repo/main/ui.ps1"))) }
    $uiOk = [bool](Get-Command Ui-Process -ErrorAction SilentlyContinue)
} catch { }
if (-not $uiOk) {
    function Ui-Banner { Write-Host ''; Write-Host '  FATURA OCR' -ForegroundColor Green; Write-Host '' }
    function Ui-Ok([string]$label, [string]$what = 'OK') { Write-Host "  > $label ... $what" -ForegroundColor Green }
    function Ui-Process([string]$label, [string]$file, [string]$arguments, [string]$dir = (Get-Location).Path) {
        $p = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $dir -NoNewWindow -PassThru -Wait
        if ($p.ExitCode -ne 0) { throw "$label falhou (codigo $($p.ExitCode))." }
        Ui-Ok $label
    }
    function Ui-Download([string]$label, [string]$url, [string]$dest) { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dest; Ui-Ok $label }
    function Ui-Box([string]$color, [string[]]$lines) { Write-Host ''; foreach ($l in $lines) { Write-Host "  $l" -ForegroundColor $color } }
}

function Install-FaturaOcr {
    if (-not $env:FATURA_OCR_UPDATING) { Ui-Banner }   # atualizando pelo atalho: o logo ja esta na tela
    # 1. uv
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (Get-Command uv -ErrorAction SilentlyContinue) { Ui-Ok 'preparando' } else {
        # instala o uv (gerenciador de Python da Astral). Processo novo: liga o TLS 1.2 nele tambem (nao herda
        # a configuracao deste). A saida dele (caminhos, "reinicie o terminal") fica escondida.
        Ui-Process 'preparando' 'powershell' '-NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://astral.sh/uv/install.ps1 | iex"'
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw 'Nao deu para baixar uma parte do programa. Confira se a internet esta funcionando.'
        }
    }

    # 2. arquivos do programa
    $running = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dest\*" }
    if ($running) { throw 'O Fatura OCR esta aberto. Feche a janela preta dele e abra o instalador de novo.' }
    $src = $PSScriptRoot
    $tmp = $null
    $ver = $null
    # Rodando da pasta ja instalada (ou sem pasta, via "irm | iex"): baixa a versao mais recente.
    $isInstalled = $src -and ((Resolve-Path $src).Path.TrimEnd('\') -eq $Dest.TrimEnd('\'))
    if (-not $src -or $isInstalled -or -not (Test-Path (Join-Path $src 'pyproject.toml'))) {
        $tmp = Join-Path $env:TEMP ('fatura-ocr-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        $zip = Join-Path $tmp 'app.zip'
        # a versao mais recente publicada (o CI publica uma a cada mudanca aprovada); o atalho compara
        # com ela para oferecer atualizacao. Sem versao publicada (ou sem acesso a API), baixa o main.
        # o atalho passa a versao que ofereceu ao usuario (instala exatamente essa)
        if ($env:FATURA_OCR_TAG -cmatch '^v\d+\.\d+\.\d+$') { $ver = $env:FATURA_OCR_TAG } else {
            try { $ver = (Invoke-RestMethod -UseBasicParsing -TimeoutSec 20 -Uri "https://api.github.com/repos/$Repo/releases/latest").tag_name } catch { $ver = $null }
            if ($ver -cnotmatch '^v\d+\.\d+\.\d+$') { $ver = $null }
        }
        $ref = if ($ver) { "refs/tags/$ver" } else { 'refs/heads/main' }
        Ui-Download $(if ($ver) { "baixando $ver" } else { 'baixando' }) "https://github.com/$Repo/archive/$ref.zip" $zip
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
    Ui-Ok 'copiando arquivos'

    # 3. Python + dependencias
    # na primeira vez leva alguns minutos: a linha fica animada e mostra o que o uv esta fazendo
    Ui-Process 'componentes' (Get-Command uv).Source 'sync --frozen --no-dev' $Dest

    # 4. atalhos
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
        $lnkPath = Join-Path $dir 'Fatura OCR.lnk'
        # apaga e cria de novo: sobrescrever o mesmo arquivo nao faz a Area de Trabalho redesenhar o icone
        # (o Menu Iniciar redesenhava; a Area de Trabalho mantinha o antigo ate o atalho ser apagado)
        if (Test-Path $lnkPath) { Remove-Item -Path $lnkPath -Force }
        $lnk = $shell.CreateShortcut($lnkPath)
        $lnk.TargetPath = Join-Path $Dest 'iniciar.cmd'
        $lnk.WorkingDirectory = $Dest
        $lnk.IconLocation = $icoLnk + ',0'
        $lnk.Description = 'Fatura OCR: capturas da fatura para CSV'
        $lnk.Save()
    }
    # pede ao Windows para redesenhar os icones (Windows 10/11); se nao existir, o icone novo aparece depois
    $ie4 = Join-Path $env:SystemRoot 'System32\ie4uinit.exe'
    if (Test-Path $ie4) { try { & $ie4 -show; $global:LASTEXITCODE = 0 } catch { } }
    # e avisa o Explorer que icones mudaram (SHCNE_ASSOCCHANGED): a Area de Trabalho redesenha os atalhos
    try {
        if (-not ('FaturaOcr.Shell' -as [type])) {   # segunda instalacao na mesma janela: o tipo ja existe
            Add-Type -Namespace FaturaOcr -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'
        }
        [FaturaOcr.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    } catch { }
    Ui-Ok 'atalho'

    if (-not $env:FATURA_OCR_UPDATING) { Ui-Box Green @('PRONTO.  Abra pelo atalho "Fatura OCR".') }
    if ($env:CI) { return }   # CI (GitHub Actions): sem pergunta
    if ($env:FATURA_OCR_UPDATING) { return }   # atualizacao pedida pelo atalho: ele mesmo abre a versao nova
    $answer = Read-Host 'Abrir o Fatura OCR agora? Enter = sim, N = nao'
    if ($answer -notmatch '^[nN]') { Start-Process -FilePath (Join-Path $Dest 'iniciar.cmd') }
}

try {
    Install-FaturaOcr
} catch {
    # sem "exit": quem colou o comando no PowerShell nao perde a janela
    Write-Host ''
    Write-Host ('Algo deu errado: ' + $_.Exception.Message) -ForegroundColor Red
    Ui-Box Red @('A instalacao parou.',
                 '1. Confira a internet; feche o Fatura OCR se estiver aberto.',
                 '2. Abra o instalador de novo.',
                 '3. Falhou de novo? Mande um print desta janela.')
    if ($env:CI) { throw }   # so no CI: falha o job em vez de terminar com sucesso
}
