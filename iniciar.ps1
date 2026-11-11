# Fatura OCR - abre o programa (servidor local + navegador).
# Use o atalho "Fatura OCR" ou clique duas vezes em "iniciar.cmd".
# Deixe a janela aberta enquanto usa o programa; feche-a para encerrar.

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
Set-Location -Path $PSScriptRoot

# visual do terminal (logo, linhas animadas); sem ele, linhas simples
$ui = Join-Path $PSScriptRoot 'ui.ps1'
if (Test-Path $ui) { try { . $ui } catch { } }
if (-not (Get-Command Ui-Line -ErrorAction SilentlyContinue)) {
    $global:FUiFancy = $false
    function Ui-Banner { Write-Host ''; Write-Host '  FATURA OCR' -ForegroundColor Green; Write-Host '' }
    function Ui-Line([string]$label, [string]$tail, [string]$color = 'Green', [switch]$Final) { if ($Final) { Write-Host "  > $label ... $tail" -ForegroundColor $color } }
    function Ui-Ok([string]$label, [string]$what = 'OK') { Ui-Line $label $what 'Green' -Final }
    function Ui-Scanner([int]$tick, [int]$w = 12) { return '' }
    function Ui-Cursor([bool]$on) { }
}

Ui-Banner

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host '  O Fatura OCR nao esta instalado direito. Abra o instalador ("instalar") de novo.' -ForegroundColor Red
    Read-Host '  Aperte Enter para fechar esta janela'
    return
}

# Versao nova publicada no GitHub? Pergunta antes de abrir. So consulta qual e a versao mais recente: nenhum dado
# seu e enviado. Sem internet (ou GitHub fora do ar), abre a versao instalada sem perguntar nada.
# FATURA_OCR_NO_UPDATE=1 desliga a consulta; no CI ela nao roda (nao ha quem responda).
$vf = Join-Path $PSScriptRoot 'VERSION'
$mine = if (Test-Path $vf) { (Get-Content -Raw $vf).Trim() } else { '' }
if (-not $env:CI -and -not $env:FATURA_OCR_NO_UPDATE) {
    Ui-Line 'versao' 'consultando...' 'DarkGreen'
    $latest = $null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $latest = (Invoke-RestMethod -UseBasicParsing -TimeoutSec 5 -Uri 'https://api.github.com/repos/lucasns97/ocr-fatura/releases/latest').tag_name
    } catch { }
    if ($latest -cnotmatch '^v\d+\.\d+\.\d+$') { $latest = $null }
    $open = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$PSScriptRoot\*" }
    if (-not $latest) {
        Ui-Ok 'versao' $(if ($mine) { "$mine (sem conexao para conferir)" } else { 'sem conexao para conferir' })
    } elseif ($latest -eq $mine) {
        Ui-Ok 'versao' "$mine (em dia)"
    } elseif ($open) {
        # ja esta aberto em outra janela: o instalador nao pode trocar os arquivos agora
        Ui-Ok 'versao' "nova: $latest" 'Yellow'
        Write-Host '  Para atualizar: feche a outra janela do Fatura OCR e abra o atalho de novo.' -ForegroundColor Yellow
    } else {
        Ui-Ok 'versao' $(if ($mine) { "nova: $latest  (sua: $mine)" } else { "nova: $latest" }) 'Yellow'
        # FATURA_OCR_ASSUME_UPDATE=1: responde "sim" sozinho (teste automatico no CI)
        $answer = if ($env:FATURA_OCR_ASSUME_UPDATE) { 's' } else { Read-Host '  Atualizar agora? (1 a 2 min, seus dados ficam)  Enter = sim, N = depois' }
        if ($answer -notmatch '^[nN]') {
            # o instalador troca os arquivos desta pasta; este script ja esta na memoria e segue depois
            $env:FATURA_OCR_UPDATING = '1'
            $env:FATURA_OCR_TAG = $latest   # instala exatamente a versao oferecida
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'instalar.ps1')
            Remove-Item Env:FATURA_OCR_UPDATING, Env:FATURA_OCR_TAG -ErrorAction SilentlyContinue
            $now = if (Test-Path $vf) { (Get-Content -Raw $vf).Trim() } else { '' }
            $whole = (Test-Path (Join-Path $PSScriptRoot 'pyproject.toml')) -and (Test-Path (Join-Path $PSScriptRoot 'iniciar.cmd'))
            if (-not $whole) {
                # parou depois de apagar os arquivos antigos: nao ha versao para abrir
                Write-Host '  A atualizacao parou no meio e o programa ficou incompleto.' -ForegroundColor Red
                Write-Host '  Para consertar, instale de novo do mesmo jeito da primeira vez. Seus dados ficam.'
                Read-Host '  Aperte Enter para fechar esta janela'
                return
            } elseif ($now -eq $latest) {
                Ui-Ok 'atualizado' $latest
            } else {
                Ui-Ok 'atualizacao' 'nao deu certo; abrindo a versao que voce ja tinha' 'Yellow'
            }
        } else {
            Ui-Ok 'atualizacao' 'fica para depois' 'DarkGray'
        }
    }
}

# Sem animacao (CI, saida redirecionada): roda direto, como sempre foi.
if (-not $global:FUiFancy) {
    & uv run --frozen --no-dev fatura @args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  O Fatura OCR fechou com um erro (codigo $LASTEXITCODE)." -ForegroundColor Red
        Write-Host '  Tente abrir o atalho de novo. Se continuar, abra o instalador de novo.'
        Read-Host '  Aperte Enter para fechar esta janela'
    }
    return
}

# Com animacao: o servidor roda por baixo (saida num arquivo temporario) e esta janela vira um painel ao vivo.
# Tudo o que aparece e real: tempo ligado e o tempo de resposta do servidor (consultado a cada 5 s).
$log = Join-Path $env:TEMP ('fatura-ocr-' + $PID + '.log')
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'
$argLine = 'run --frozen --no-dev fatura'
if ($args.Count) { $argLine += ' ' + ($args -join ' ') }
$p = Start-Process -FilePath (Get-Command uv).Source -ArgumentList $argLine -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
$null = $p.Handle   # sem isso o ExitCode pode vir vazio no PowerShell 5
$B = [string][char]0x2588
try {
    Ui-Cursor $false
    $url = $null; $t = 0
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while (-not $p.HasExited) {
        if (-not $url) {
            $m = Select-String -Path $log -Pattern 'http://127\.0\.0\.1:\d+/' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value }
        }
        if ($url -and $t % 4 -eq 0) {
            try { if ((Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2).StatusCode -eq 200) { break } } catch { }
        }
        Ui-Line 'iniciando' ((Ui-Scanner $t) + ('  {0:N0}s' -f $sw.Elapsed.TotalSeconds)) 'DarkGreen'
        Start-Sleep -Milliseconds 150
        $t++
    }
    if (-not $p.HasExited) {
        Ui-Ok 'iniciando' 'ONLINE'
        Write-Host ''
        Write-Host '  NAO feche esta janela enquanto usa o Fatura OCR.' -ForegroundColor Yellow
        Write-Host "  $url" -ForegroundColor DarkGray
        Write-Host ''
        $sw.Restart(); $ping = '...'; $next = 0
        while (-not $p.HasExited) {
            if ($sw.Elapsed.TotalSeconds -ge $next) {
                $next += 5
                $q = [Diagnostics.Stopwatch]::StartNew()
                try { $null = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2; $ping = "$($q.ElapsedMilliseconds) ms" } catch { $ping = 'sem resposta' }
            }
            Write-Host -NoNewline "`r  "
            Write-Host -NoNewline $B -ForegroundColor $(if ($t % 8 -lt 4) { 'Green' } else { 'DarkGreen' })
            Write-Host -NoNewline ' ONLINE  ' -ForegroundColor Green
            Write-Host -NoNewline ('{0:hh\:mm\:ss}  ' -f $sw.Elapsed) -ForegroundColor Gray
            Write-Host -NoNewline ("resposta $ping").PadRight(22) -ForegroundColor DarkGray
            Write-Host -NoNewline (Ui-Scanner $t 10) -ForegroundColor DarkGreen
            Start-Sleep -Milliseconds 200
            $t++
        }
    }
    # o servidor parou sozinho (erro): mostra o fim do log e o que fazer
    $p.WaitForExit()
    Write-Host ''
    if ($p.ExitCode -ne 0) {
        Write-Host "  O Fatura OCR fechou com um erro (codigo $($p.ExitCode))." -ForegroundColor Red
        Get-Content -Path "$log.err", $log -Tail 8 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        Write-Host '  Tente abrir o atalho de novo. Se continuar, abra o instalador de novo.'
        Read-Host '  Aperte Enter para fechar esta janela'
    }
} finally {
    Ui-Cursor $true
    # o uv abre o Python como filho: encerra os dois juntos
    if (-not $p.HasExited) { & taskkill.exe /PID $p.Id /T /F 2>$null | Out-Null }
    Remove-Item -Path $log, "$log.err" -Force -ErrorAction SilentlyContinue
}
