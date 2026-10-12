@echo off
rem ASCII only: cmd misreads UTF-8 Korean lines on code page 949 PCs (WORKPC ran them as commands).
rem Builds PyWinAudio Auto Master as a 64-bit VST2 DLL with the Visual Studio 2022 C compiler.
setlocal
set HERE=%~dp0
for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set VS=%%i
if not defined VS (echo [ ERROR ] Visual Studio 2022 C++ build tools not found & exit /b 1)
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
if not exist "%HERE%build" mkdir "%HERE%build"
cl /nologo /O2 /fp:fast /MT /W3 /D_CRT_SECURE_NO_WARNINGS /D_USE_MATH_DEFINES /LD "%HERE%automaster.c" /Fo"%HERE%build\\" /Fe"%HERE%build\PyWinAudioAutoMaster.dll" advapi32.lib /link /DEF:"%HERE%automaster.def" || exit /b 1
echo [ BUILT ] %HERE%build\PyWinAudioAutoMaster.dll
