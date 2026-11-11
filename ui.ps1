# Fatura OCR - visual do terminal (verde, animado, pouco texto). Usado por instalar.ps1 e iniciar.ps1.
# So ASCII neste arquivo (o PowerShell 5 do Windows estraga acentos): os blocos e simbolos vem de [char].
# Com a saida redirecionada (CI, log) nao ha animacao: so linhas simples. FATURA_OCR_FANCY=1 forca a animacao.

$global:FUiFancy = ($env:FATURA_OCR_FANCY -eq '1') -or -not ([Console]::IsOutputRedirected -or $env:CI)
$global:FUiB = @{ full = [string][char]0x2588; dark = [string][char]0x2593; mid = [string][char]0x2592; light = [string][char]0x2591 }
$global:FUiSpin = @('|', '/', '-', '\')

function Ui-Cursor([bool]$on) { if ($global:FUiFancy) { try { [Console]::CursorVisible = $on } catch { } } }

function Ui-Fit([string]$s, [int]$n) {
    # uma linha so, no maximo n caracteres (os blocos do scanner ficam; texto de fora passa por Ui-Plain)
    $s = ($s -replace '[\x00-\x1F]', ' ').TrimEnd()
    if ($s.Length -gt $n) { $s = $s.Substring(0, $n - 3) + '...' }
    return $s.PadRight($n)
}

function Ui-Banner {
    $logo = @(
        ' _____ _  _____ _   _ ____      _       ___   ____ ____  ',
        '|  ___/ \|_   _| | | |  _ \    / \     / _ \ / ___|  _ \ ',
        '| |_ / _ \ | | | | | | |_) |  / _ \   | | | | |   | |_) |',
        '|  _/ ___ \| | | |_| |  _ <  / ___ \  | |_| | |___|  _ < ',
        '|_|/_/   \_\_|  \___/|_| \_\/_/   \_\  \___/ \____|_| \_\'
    )
    Write-Host ''
    if ($global:FUiFancy) {
        # chuva de 0 e 1 por um instante, depois o logo aparece linha a linha
        try {
            Ui-Cursor $false
            # reserva as linhas antes (no fim da tela, desenhar rolaria lixo para cima)
            foreach ($l in $logo) { Write-Host '' }
            $top = [Console]::CursorTop - $logo.Count
            $rnd = New-Object Random
            for ($f = 0; $f -lt 10; $f++) {
                [Console]::SetCursorPosition(0, $top)
                foreach ($l in $logo) {
                    $row = -join (1..$l.Length | ForEach-Object { if ($rnd.Next(4) -eq 0) { [string]$rnd.Next(2) } else { ' ' } })
                    Write-Host $row -ForegroundColor DarkGreen
                }
                Start-Sleep -Milliseconds 45
            }
            [Console]::SetCursorPosition(0, $top)
        } catch { }
        foreach ($l in $logo) { Write-Host $l -ForegroundColor Green; Start-Sleep -Milliseconds 35 }
        Ui-Cursor $true
    } else {
        foreach ($l in $logo) { Write-Host $l -ForegroundColor Green }
    }
    Write-Host ''
}

# texto vindo de outros programas: so ASCII visivel (pode ter cores, barras de progresso, acentos estragados)
function Ui-Plain([string]$s) { return ($s -replace '\x1B\[[0-9;]*[A-Za-z]', '' -replace '[^\x20-\x7E]', '').Trim() }

function Ui-Size([long]$bytes) { if ($bytes -lt 1MB) { '{0:N0} KB' -f ($bytes / 1KB) } else { '{0:N1} MB' -f ($bytes / 1MB) } }

# uma linha de passo:  > baixando ............ OK
function Ui-Line([string]$label, [string]$tail, [string]$color = 'Green', [switch]$Final) {
    $dots = ' ' + ('.' * [Math]::Max(2, 26 - $label.Length)) + ' '
    if ($global:FUiFancy) {
        Write-Host -NoNewline "`r  > " -ForegroundColor DarkGreen
        Write-Host -NoNewline ($label + $dots) -ForegroundColor Gray
        # cabe na janela: uma linha que quebra faria cada quadro da animacao virar uma linha nova
        $w = 46; try { $w = [Math]::Min(46, [Math]::Max(10, [Console]::WindowWidth - 5 - $label.Length - $dots.Length)) } catch { }
        Write-Host -NoNewline (Ui-Fit $tail $w) -ForegroundColor $color
        if ($Final) { Write-Host '' }
    } elseif ($Final) {
        Write-Host ('  > ' + $label + $dots + $tail.Trim())
    }
}
function Ui-Ok([string]$label, [string]$what = 'OK', [string]$color = 'Green') { Ui-Line $label $what $color -Final }

# faixa que vai e volta (scanner), em blocos
function Ui-Scanner([int]$tick, [int]$w = 12) {
    $pos = $tick % (2 * ($w - 1)); if ($pos -ge $w) { $pos = 2 * ($w - 1) - $pos }
    $s = ''
    for ($i = 0; $i -lt $w; $i++) {
        $d = [Math]::Abs($i - $pos)
        $s += if ($d -eq 0) { $global:FUiB.full } elseif ($d -eq 1) { $global:FUiB.dark } elseif ($d -eq 2) { $global:FUiB.mid } else { $global:FUiB.light }
    }
    return $s
}

# Roda um programa sem janela nova e anima ate ele terminar. A ultima linha que ele escreveu aparece apagada
# ao lado (o que de fato esta acontecendo). Erro: mostra o fim da saida dele e lanca excecao.
function Ui-Process([string]$label, [string]$file, [string]$arguments, [string]$dir = (Get-Location).Path) {
    $out = [IO.Path]::GetTempFileName(); $err = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $dir -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        $null = $p.Handle   # sem isso o ExitCode pode vir vazio no PowerShell 5
        $t = 0
        Ui-Cursor $false
        while (-not $p.HasExited) {
            $last = ''
            try {
                $tail = Get-Content -Path $err, $out -Tail 1 -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_.Trim() } | Select-Object -Last 1
                if ($tail) { $last = Ui-Plain ([string]$tail) }
            } catch { }
            Ui-Line $label ((Ui-Scanner $t) + '  ' + $global:FUiSpin[$t % 4] + ' ' + $last) 'DarkGreen'
            Start-Sleep -Milliseconds 120
            $t++
        }
        $p.WaitForExit()
        Ui-Cursor $true
        if ($p.ExitCode -ne 0) {
            Ui-Line $label "ERRO (codigo $($p.ExitCode))" 'Red' -Final
            Get-Content -Path $err, $out -Tail 15 -Encoding UTF8 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            throw "$label falhou (codigo $($p.ExitCode))."
        }
        Ui-Ok $label
    } finally {
        Ui-Cursor $true
        Remove-Item -Path $out, $err -Force -ErrorAction SilentlyContinue
    }
}

# Baixa um arquivo mostrando quanto ja chegou (o GitHub nao informa o tamanho total do zip).
function Ui-Download([string]$label, [string]$url, [string]$dest) {
    $wc = New-Object Net.WebClient
    $task = $wc.DownloadFileTaskAsync($url, $dest)
    $t = 0
    Ui-Cursor $false
    try {
        while (-not $task.IsCompleted) {
            $n = 0; if (Test-Path $dest) { $n = (Get-Item $dest).Length }
            Ui-Line $label ((Ui-Scanner $t) + '  ' + (Ui-Size $n)) 'DarkGreen'
            Start-Sleep -Milliseconds 100
            $t++
        }
        if ($task.IsFaulted) { throw $task.Exception.GetBaseException() }
        Ui-Ok $label ('OK  (' + (Ui-Size (Get-Item $dest).Length) + ')')
    } finally { Ui-Cursor $true; if (-not $task.IsCompleted) { $wc.CancelAsync() }; $wc.Dispose() }
}

function Ui-Box([string]$color, [string[]]$lines) {
    $w = ($lines | Measure-Object -Property Length -Maximum).Maximum + 4
    $bar = '+' + ('-' * $w) + '+'
    Write-Host ''
    Write-Host "  $bar" -ForegroundColor $color
    foreach ($l in $lines) { Write-Host ('  |  ' + $l.PadRight($w - 2) + '|') -ForegroundColor $color }
    Write-Host "  $bar" -ForegroundColor $color
}
