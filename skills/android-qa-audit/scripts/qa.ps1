# qa <serial|-> <command> [args…] — short call of adb_helpers.py (Windows PowerShell). Adds --serial <serial> and,
# if $env:QA_RUN_DIR (or $env:ANDROID_QA_RUN_DIR) is set, --run-dir. «-» instead of a serial: ANDROID_SERIAL or the
# only device.   .\qa.ps1 emulator-5554 dump-ui --texts
$ErrorActionPreference = 'Stop'
if ($args.Count -lt 2) { Write-Error 'usage: qa <serial|-> <adb_helpers.py command> [args…]'; exit 2 }
$py = $null
foreach ($c in @(@('py', '-3'), @('python'), @('python3'))) {
  if (Get-Command $c[0] -ErrorAction SilentlyContinue) { $py = $c; break }
}
if (-not $py) { Write-Error 'Python 3.9+ не найден'; exit 127 }
$serial = $args[0]; $cmd = $args[1]
$rest = @(); if ($args.Count -gt 2) { $rest = $args[2..($args.Count - 1)] }
$rd = $env:QA_RUN_DIR; if (-not $rd) { $rd = $env:ANDROID_QA_RUN_DIR }
$opts = @()
if ($serial -ne '-') { $opts += @('--serial', $serial) }
if ($rd) { $opts += @('--run-dir', $rd) }
$script = Join-Path $PSScriptRoot 'adb_helpers.py'
$exe = $py[0]; $pre = @(); if ($py.Count -gt 1) { $pre = $py[1..($py.Count - 1)] }
& $exe @pre $script $cmd @opts @rest
exit $LASTEXITCODE
