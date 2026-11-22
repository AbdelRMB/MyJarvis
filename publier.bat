@echo off
chcp 65001 >nul
rem Construit WesleySetup.exe sur ce PC et le publie dans les GitHub Releases (gratuit, sans limite).
rem Avant : version incrementee dans wesley\version.py, description dans CHANGELOG.md, commit pousse.
cd /d "%~dp0"
set SANS_PAUSE=1
set AUTO=
if "%~1"=="--auto" set AUTO=1
call construire.bat || goto :erreur
for /f "delims=" %%v in ('".venv\Scripts\python.exe" -c "from wesley.version import VERSION; print(VERSION)"') do set VERSION=%%v
rem + copie sous l'ancien nom : la mise a jour automatique des PC encore en version Jarvis cherche JarvisSetup-x.y.z.exe
copy /y "installateur\WesleySetup-%VERSION%.exe" "installateur\JarvisSetup-%VERSION%.exe" >nul
".venv\Scripts\python.exe" publier.py "installateur\WesleySetup-%VERSION%.exe" "installateur\JarvisSetup-%VERSION%.exe" || goto :erreur
if not defined AUTO pause
exit /b 0
:erreur
echo Echec de la publication.
if not defined AUTO pause
exit /b 1
