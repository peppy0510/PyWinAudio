@echo off
rem PyWinAudio Leveler 를 64 비트 VST2 DLL 로 만든다. Visual Studio 2022 의 C 컴파일러를 쓴다.
setlocal
set HERE=%~dp0
for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set VS=%%i
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
if not exist "%HERE%build" mkdir "%HERE%build"
cl /nologo /O2 /fp:fast /MT /W3 /D_CRT_SECURE_NO_WARNINGS /D_USE_MATH_DEFINES /LD "%HERE%leveler.c" /Fo"%HERE%build\\" /Fe"%HERE%build\PyWinAudioLeveler.dll" advapi32.lib /link /DEF:"%HERE%leveler.def" || exit /b 1
echo [ BUILT ] %HERE%build\PyWinAudioLeveler.dll
