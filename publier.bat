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
".venv\Scripts\python.exe" publier.py "installateur\WesleySetup-%VERSION%.exe" || goto :erreur
if not defined AUTO pause
exit /b 0
:erreur
echo Echec de la publication.
if not defined AUTO pause
exit /b 1
