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
    if ($latest -and $latest -ne $mine) {
        Write-Host ''
        $have = if ($mine) { "instalada: $mine" } else { 'versao instalada desconhecida' }
        Write-Host "Ha uma versao nova do Fatura OCR: $latest ($have)." -ForegroundColor Yellow
        $answer = Read-Host 'Atualizar agora? Leva cerca de 1 minuto. [S/n]'
        if ($answer -notmatch '^[nN]') {
            # o instalador troca os arquivos desta pasta; este script ja esta na memoria e segue depois
            $env:FATURA_OCR_UPDATING = '1'
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'instalar.ps1')
            Remove-Item Env:FATURA_OCR_UPDATING -ErrorAction SilentlyContinue
            $now = if (Test-Path $vf) { (Get-Content -Raw $vf).Trim() } else { '' }
            if ($now -eq $latest) {
                Write-Host 'Atualizado! Abrindo a versao nova...' -ForegroundColor Green
            } else {
                Write-Host 'A atualizacao nao terminou (veja a mensagem acima). Vamos abrir a versao instalada.' -ForegroundColor Yellow
                Write-Host 'Para tentar de novo: feche esta janela e abra o atalho de novo, ou rode o instalar.cmd.'
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
