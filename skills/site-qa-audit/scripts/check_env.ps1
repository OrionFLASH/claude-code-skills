# Проверка окружения site-qa-audit. Аргументы передаются в check_env.py (--fast, --json FILE, --no-browsers).
$ErrorActionPreference = 'Stop'
$py = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
& $py (Join-Path $PSScriptRoot 'check_env.py') @args
exit $LASTEXITCODE
