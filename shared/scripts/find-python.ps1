# Возвращает команду Python 3 (py -3, python3 или python). Подключается через dot-source.
$script:PYTHON = $null
foreach ($c in @('python3', 'python')) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        & $c -c "import sys; sys.exit(sys.version_info[0]!=3)" 2>$null
        if ($LASTEXITCODE -eq 0) { $script:PYTHON = $c; break }
    }
}
if (-not $script:PYTHON) { Write-Error "Нужен Python 3"; exit 1 }
