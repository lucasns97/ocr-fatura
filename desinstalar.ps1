# Fatura OCR - remove o programa e os atalhos.
# Mantem %USERPROFILE%\.fatura-ocr (nomes de estabelecimentos que voce corrigiu); apague a mao se quiser.
$Dest = Join-Path $env:LOCALAPPDATA 'FaturaOCR'
$running = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dest\*" }
if ($running) { Write-Host 'O Fatura OCR esta aberto. Feche a janela dele e rode de novo.' -ForegroundColor Red; return }
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    if (-not $dir) { continue }
    $lnk = Join-Path $dir 'Fatura OCR.lnk'
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "Atalho removido: $lnk" }
}
# nao da para apagar a pasta em que estamos
Set-Location $env:TEMP
[Environment]::CurrentDirectory = $env:TEMP
if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $Dest) {
    Write-Host "Alguns arquivos ficaram em $Dest (em uso). Apague essa pasta a mao." -ForegroundColor Yellow
} else {
    Write-Host 'Fatura OCR desinstalado.' -ForegroundColor Green
}
