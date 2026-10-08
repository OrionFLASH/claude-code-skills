# Проверка окружения android-qa-audit (только чтение). Аргументы передаются в check_env.py (--fast, --no-devices, --json FILE).
$ErrorActionPreference = 'Stop'
$py = $null
foreach ($c in @('python3', 'python')) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        & $c -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = @($c); break }
    }
}
if (-not $py -and (Get-Command py -ErrorAction SilentlyContinue)) { $py = @('py', '-3') }
if (-not $py) { Write-Error 'Нужен Python 3.9+ (python.org или winget install Python.Python.3.12)'; exit 1 }
$exe = $py[0]; $pre = @($py | Select-Object -Skip 1)
& $exe @pre (Join-Path $PSScriptRoot 'check_env.py') @args
exit $LASTEXITCODE
