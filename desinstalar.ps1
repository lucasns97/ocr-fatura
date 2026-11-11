# Fatura OCR - remove o programa e os atalhos.
# Mantem %USERPROFILE%\.fatura-ocr (nomes de estabelecimentos que voce corrigiu); apague a mao se quiser.
$Dest = Join-Path $env:LOCALAPPDATA 'FaturaOCR'
$running = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dest\*" }
if ($running) { Write-Host 'O Fatura OCR esta aberto. Feche a janela preta dele e abra o desinstalador de novo.' -ForegroundColor Red; return }
foreach ($place in @(@('Desktop', 'da Area de Trabalho'), @('Programs', 'do Menu Iniciar'))) {
    $dir = [Environment]::GetFolderPath($place[0])
    if (-not $dir) { continue }
    $lnk = Join-Path $dir 'Fatura OCR.lnk'
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host ('Atalho removido ' + $place[1]) }
}
# nao da para apagar a pasta em que estamos
Set-Location $env:TEMP
[Environment]::CurrentDirectory = $env:TEMP
if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $Dest) {
    Write-Host "Quase tudo removido. Reinicie o computador e depois apague a pasta $Dest (cole esse endereco na barra do Explorador de Arquivos)." -ForegroundColor Yellow
} else {
    Write-Host 'Fatura OCR removido. Os nomes de lojas que voce corrigiu ficam guardados, caso instale de novo.' -ForegroundColor Green
}
