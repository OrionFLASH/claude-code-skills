# Обёртка над tools/lib/skillsrepo.py (new). См. README.md.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $Root 'shared/scripts/find-python.ps1')
& $PYTHON (Join-Path $Root 'tools/lib/skillsrepo.py') new @args
exit $LASTEXITCODE
