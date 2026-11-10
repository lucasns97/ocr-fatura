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

Write-Host 'Abrindo o Fatura OCR no navegador...'
Write-Host 'Deixe esta janela aberta enquanto usa o programa. Para encerrar, feche-a.'
& uv run --frozen --no-dev fatura @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "O programa parou com erro (codigo $LASTEXITCODE). Tente rodar o instalar.cmd de novo." -ForegroundColor Red
    Read-Host 'Aperte Enter para fechar'
}
