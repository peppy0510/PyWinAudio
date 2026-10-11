# PyWinAudio Leveler 를 Equalizer APO 엔진(audiodg)이 읽을 수 있는 곳에 깐다.
# 엔진이 쥐고 있는 옛 DLL 은 덮어쓸 수 없어 이름을 바꿔 두고 새 것을 넣는다. 새 것은 오디오
# 서비스가 다시 시작할 때 올라가고, 남은 옛 파일은 그다음 설치 때 지운다.
param([string]$Source = (Join-Path $PSScriptRoot 'build\PyWinAudioLeveler.dll'))
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Source `"$Source`""
    exit
}
if (-not (Test-Path $Source)) { Write-Error "Not built yet: $Source (run build.cmd)"; exit 1 }
$target = 'C:\Program Files\VSTPlugIns\PyWinAudio'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Get-ChildItem "$target\PyWinAudioLeveler.old-*.dll" -ErrorAction SilentlyContinue | Remove-Item -ErrorAction SilentlyContinue
$dll = Join-Path $target 'PyWinAudioLeveler.dll'
try { Copy-Item $Source $dll -Force -ErrorAction Stop; "Installed $dll" }
catch {
    Rename-Item $dll ('PyWinAudioLeveler.old-' + (Get-Date -Format 'yyyyMMddHHmmss') + '.dll')
    Copy-Item $Source $dll -Force
    "Installed $dll (the running engine keeps the old one until the audio service restarts)"
}
