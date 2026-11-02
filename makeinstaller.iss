; http://www.jrsoftware.org/ishelp/index.php

; each install puts Auto Master in a new folder: the engine loads a new path without restarting audio
#define Stamp GetDateTimeString('yyyymmddhhnnss', '', '')

[Setup]
AppName="PyWinAudio"
AppVerName="PyWinAudio 0.1.0"
DefaultDirName="{autopf}\PyWinAudio"
DefaultGroupName="PyWinAudio"
AppVersion="0.1.0"
AppCopyright="Taehong Kim"
AppPublisher="Taehong Kim"
UninstallDisplayIcon="{app}\PyWinAudio.exe"
Compression=lzma2/max
SolidCompression=yes
OutputDir=".dist"
OutputBaseFilename="PyWinAudio-0.1.0-Setup"
; VersionInfoVersion="0.1.0"
VersionInfoProductVersion="0.1.0"
VersionInfoCompany="Taehong Kim"
VersionInfoCopyright="Taehong Kim"
ArchitecturesInstallIn64BitMode="x64compatible"
CloseApplications=yes
RestartApplications=no

[Files]
Source: ".dist\*"; DestDir: "{app}"; Flags: recursesubdirs
; the rack keeps pointing at it, so uninstalling leaves it where the engine reads it
Source: "plugin\.build\PyWinAudioAutoMaster.dll"; DestDir: "{commonappdata}\PyWinAudio\vstplugins\PyWinAudioAutoMaster\{#Stamp}"; Flags: uninsneveruninstall

[Run]
; the engine runs as LOCAL SERVICE; as in plugin\install.ps1
Filename: "{win}\System32\icacls.exe"; Parameters: """{commonappdata}\PyWinAudio\vstplugins"" /grant *S-1-5-19:(OI)(CI)RX"; Flags: runhidden
Filename: "{app}\PyWinAudio.exe"; Description: "Launch PyWinAudio"; Flags: nowait postinstall skipifsilent

[Icons]
Name: "{group}\PyWinAudio"; Filename: "{app}\PyWinAudio.exe"
Name: "{commondesktop}\PyWinAudio"; Filename: "{app}\PyWinAudio.exe"
