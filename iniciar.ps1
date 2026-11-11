# Fatura OCR - abre o programa (servidor local + navegador).
# Use o atalho "Fatura OCR" ou clique duas vezes em "iniciar.cmd".
# Deixe a janela aberta enquanto usa o programa; feche-a para encerrar.

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'O Fatura OCR nao esta instalado direito. Abra o instalador ("instalar") de novo.' -ForegroundColor Red
    Read-Host 'Aperte Enter para fechar esta janela'
    return
}

# Versao nova publicada no GitHub? Pergunta antes de abrir. So consulta qual e a versao mais recente: nenhum dado
# seu e enviado. Sem internet (ou GitHub fora do ar), abre a versao instalada sem perguntar nada.
# FATURA_OCR_NO_UPDATE=1 desliga a consulta; no CI ela nao roda (nao ha quem responda).
if (-not $env:CI -and -not $env:FATURA_OCR_NO_UPDATE) {
    $latest = $null
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $latest = (Invoke-RestMethod -UseBasicParsing -TimeoutSec 5 -Uri 'https://api.github.com/repos/lucasns97/ocr-fatura/releases/latest').tag_name
    } catch { }
    $vf = Join-Path $PSScriptRoot 'VERSION'
    $mine = if (Test-Path $vf) { (Get-Content -Raw $vf).Trim() } else { '' }
    if ($latest -cnotmatch '^v\d+\.\d+\.\d+$') { $latest = $null }
    $open = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$PSScriptRoot\*" }
    if ($latest -and $latest -ne $mine -and $open) {
        # ja esta aberto em outra janela: o instalador nao pode trocar os arquivos agora
        Write-Host ''
        Write-Host 'Tem uma versao nova do Fatura OCR. Para atualizar: feche a outra janela preta do Fatura OCR e abra o atalho de novo.' -ForegroundColor Yellow
    } elseif ($latest -and $latest -ne $mine) {
        Write-Host ''
        $have = if ($mine) { "; a sua e $mine" } else { '' }
        Write-Host "Tem uma versao nova do Fatura OCR ($latest$have)." -ForegroundColor Yellow
        # FATURA_OCR_ASSUME_UPDATE=1: responde "sim" sozinho (teste automatico no CI)
        $answer = if ($env:FATURA_OCR_ASSUME_UPDATE) { 's' } else { Read-Host 'Atualizar agora? Leva 1 a 2 minutos e seus dados ficam. Enter = sim, N = depois' }
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
                Write-Host 'A atualizacao parou no meio e o programa ficou incompleto.' -ForegroundColor Red
                Write-Host 'Para consertar, instale de novo do mesmo jeito da primeira vez. Seus dados ficam.'
                Read-Host 'Aperte Enter para fechar esta janela'
                return
            } elseif ($now -eq $latest) {
                Write-Host "Tudo certo, atualizado para $latest. Abrindo..." -ForegroundColor Green
            } else {
                Write-Host 'A atualizacao nao deu certo; vamos abrir a versao que voce ja tinha.' -ForegroundColor Yellow
                Write-Host 'Para tentar de novo outra hora, e so abrir o atalho.'
            }
        } else {
            Write-Host 'Ok, fica para depois. O atalho pergunta de novo na proxima vez.'
        }
    }
}

# o aviso mais importante: fechar esta janela fecha o programa
$bar = '-' * 50
Write-Host ''
Write-Host $bar -ForegroundColor Yellow
Write-Host '  O Fatura OCR esta abrindo no seu navegador.' -ForegroundColor Yellow
Write-Host '  NAO feche esta janela enquanto estiver usando.' -ForegroundColor Yellow
Write-Host '  Terminou? Pode fechar esta janela.' -ForegroundColor Yellow
Write-Host $bar -ForegroundColor Yellow
& uv run --quiet --frozen --no-dev fatura @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "O Fatura OCR fechou com um erro (codigo $LASTEXITCODE)." -ForegroundColor Red
    Write-Host 'Tente abrir o atalho de novo. Se continuar, abra o instalador de novo.'
    Read-Host 'Aperte Enter para fechar esta janela'
}
