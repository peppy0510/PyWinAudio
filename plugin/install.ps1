# PyWinAudio Auto Master 를 Equalizer APO 엔진(audiodg)이 읽을 수 있는 보관소에 빌드마다 새 폴더로 깐다.
# 엔진은 이미 올린 DLL 을 같은 경로로 다시 올리면 옛 것을 돌려준다 — 경로가 새로우면 새 DLL 이 따로 올라가므로
# 오디오 서비스를 다시 시작할 필요가 없다. 앱이 켜질 때 가장 새 폴더로 랙 경로를 옮긴다.
# 보관소는 사용자 프로필 밖(ProgramData)이라 관리자 권한도 필요 없다. 옛 폴더는 최근 셋만 남기고,
# 엔진이 아직 쥐고 있는 것은 지워지지 않으니 다음 설치 때 다시 지운다.
param([string]$Source = (Join-Path $PSScriptRoot 'build\PyWinAudioAutoMaster.dll'))
if (-not (Test-Path $Source)) { Write-Error "Not built yet: $Source (run build.cmd)"; exit 1 }
$store = Join-Path $env:ProgramData 'PyWinAudio\vstplugins'
if (-not (Test-Path $store)) {
    New-Item -ItemType Directory -Force -Path $store | Out-Null
    icacls $store /grant '*S-1-5-19:(OI)(CI)RX' | Out-Null
}
$family = Join-Path $store 'PyWinAudioAutoMaster'
$target = Join-Path $family (Get-Date -Format 'yyyyMMddHHmmss')
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item $Source (Join-Path $target 'PyWinAudioAutoMaster.dll') -Force -ErrorAction Stop
"Installed $target\PyWinAudioAutoMaster.dll (PyWinAudio switches to it when it starts)"
Get-ChildItem $family -Directory | Sort-Object Name -Descending | Select-Object -Skip 3 |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
