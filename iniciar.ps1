# Fatura OCR - abre o programa (servidor local + navegador).
# Use o atalho "Fatura OCR" ou clique duas vezes em "iniciar.cmd".
# Deixe a janela aberta enquanto usa o programa; feche-a para encerrar.

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'O uv nao foi encontrado. Rode primeiro o "instalar.cmd".' -ForegroundColor Red
    Read-Host 'Aperte Enter para fechar'
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
        Write-Host "Ha uma versao nova do Fatura OCR ($latest). Para atualizar, feche o Fatura OCR que ja esta aberto e abra o atalho de novo." -ForegroundColor Yellow
    } elseif ($latest -and $latest -ne $mine) {
        Write-Host ''
        $have = if ($mine) { "instalada: $mine" } else { 'versao instalada desconhecida' }
        Write-Host "Ha uma versao nova do Fatura OCR: $latest ($have)." -ForegroundColor Yellow
        # FATURA_OCR_ASSUME_UPDATE=1: responde "sim" sozinho (teste automatico no CI)
        $answer = if ($env:FATURA_OCR_ASSUME_UPDATE) { 's' } else { Read-Host 'Atualizar agora? Costuma levar 1 a 2 minutos. [S/n]' }
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
                Write-Host 'Para reinstalar, rode de novo o comando de instalacao do README (item A).'
                Read-Host 'Aperte Enter para fechar'
                return
            } elseif ($now -eq $latest) {
                Write-Host "Atualizado para $latest! Abrindo a versao nova..." -ForegroundColor Green
            } else {
                Write-Host 'A atualizacao nao terminou (veja a mensagem acima). Vamos abrir a versao instalada.' -ForegroundColor Yellow
                Write-Host 'Para tentar de novo: feche esta janela e abra o atalho de novo.'
            }
        } else {
            Write-Host 'Ok, abrindo a versao instalada. Para atualizar depois, e so abrir o atalho de novo.'
        }
    }
}

Write-Host 'Abrindo o Fatura OCR no navegador...'
Write-Host 'Deixe esta janela aberta enquanto usa o programa. Para encerrar, feche-a.'
& uv run --frozen --no-dev fatura @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "O programa parou com erro (codigo $LASTEXITCODE). Tente rodar o instalar.cmd de novo." -ForegroundColor Red
    Read-Host 'Aperte Enter para fechar'
}
