# Ставит скилы в ~/.claude/skills: junction на Windows, симлинк на macOS/Linux.
#   tools\install.ps1                 — все скилы
#   tools\install.ps1 a b             — выбранные
#   tools\install.ps1 -Uninstall a    — убрать ссылки
param([switch]$Uninstall, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Names)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Target = if ($env:CLAUDE_SKILLS_DIR) { $env:CLAUDE_SKILLS_DIR } else { Join-Path $HOME '.claude/skills' }
if (-not $Names) { $Names = Get-ChildItem (Join-Path $Root 'skills') -Directory | ForEach-Object Name }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
$isWin = ($PSVersionTable.PSEdition -eq 'Desktop') -or $IsWindows
foreach ($name in $Names) {
    $src = Join-Path $Root "skills/$name"; $dst = Join-Path $Target $name
    if (-not (Test-Path (Join-Path $src 'SKILL.md'))) { Write-Host "SKIP  ${name}: нет SKILL.md"; continue }
    $item = Get-Item $dst -Force -ErrorAction SilentlyContinue
    $isLink = $item -and $item.LinkType
    if ($Uninstall) {
        if ($isLink) { $item.Delete(); Write-Host "REMOVED $dst" } else { Write-Host "SKIP  ${dst}: не ссылка" }
        continue
    }
    if ($isLink) {
        if (($item.Target | Select-Object -First 1) -eq $src) { Write-Host "OK    $name (уже установлен)"; continue }
        $item.Delete()
    } elseif ($item) {
        Write-Host "SKIP  ${name}: $dst существует и не является ссылкой"
        if (Test-Path (Join-Path $dst $name)) { Write-Host "WARN  ${name}: внутри $dst есть вложенная папка '$name' (копия легла внутрь старой). Удалите её и обновите поверх: Copy-Item -Recurse -Force <новая>\* $dst\" }
        continue
    }
    $type = if ($isWin) { 'Junction' } else { 'SymbolicLink' }
    New-Item -ItemType $type -Path $dst -Target $src | Out-Null
    Write-Host "LINKED $dst -> $src ($type)"
}
