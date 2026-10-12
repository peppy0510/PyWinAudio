# PyWinAudio Auto Master 를 Equalizer APO 엔진(audiodg)이 읽을 수 있는 곳에 깐다.
# 엔진이 쥐고 있는 옛 DLL 은 덮어쓸 수 없어 이름을 바꿔 두고 새 것을 넣는다. 새 것은 설정 줄이
# 바뀌거나 오디오 서비스가 다시 시작할 때 올라가고, 남은 옛 파일은 그다음 설치 때 지운다.
# Leveler 시절 파일(PyWinAudioLeveler*.dll)도 엔진이 놓아주었으면 함께 지운다.
param([string]$Source = (Join-Path $PSScriptRoot 'build\PyWinAudioAutoMaster.dll'))
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Source `"$Source`""
    exit
}
if (-not (Test-Path $Source)) { Write-Error "Not built yet: $Source (run build.cmd)"; exit 1 }
$target = 'C:\Program Files\VSTPlugIns\PyWinAudio'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Get-ChildItem "$target\PyWinAudioAutoMaster.old-*.dll", "$target\PyWinAudioLeveler*.dll" -ErrorAction SilentlyContinue |
    Remove-Item -ErrorAction SilentlyContinue
$dll = Join-Path $target 'PyWinAudioAutoMaster.dll'
try { Copy-Item $Source $dll -Force -ErrorAction Stop; "Installed $dll" }
catch {
    Rename-Item $dll ('PyWinAudioAutoMaster.old-' + (Get-Date -Format 'yyyyMMddHHmmss') + '.dll')
    Copy-Item $Source $dll -Force
    "Installed $dll (the running engine keeps the old one until the audio service restarts)"
}
$left = @(Get-ChildItem "$target\PyWinAudioLeveler*.dll" -ErrorAction SilentlyContinue)
if ($left.Count) { 'Old Leveler files still in use by the engine (removed on the next install): ' + ($left.Name -join ', ') }
