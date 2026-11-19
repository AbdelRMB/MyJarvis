@echo off
chcp 65001 >nul
rem Construit JarvisSetup.exe sur ce PC et le publie dans les GitHub Releases (gratuit, sans limite).
rem Avant : version incrementee dans jarvis\version.py, description dans CHANGELOG.md, commit pousse.
cd /d "%~dp0"
set SANS_PAUSE=1
call construire.bat || goto :erreur
for /f "delims=" %%v in ('".venv\Scripts\python.exe" -c "from jarvis.version import VERSION; print(VERSION)"') do set VERSION=%%v
".venv\Scripts\python.exe" publier.py "installateur\JarvisSetup-%VERSION%.exe" || goto :erreur
pause
exit /b 0
:erreur
echo Echec de la publication.
pause
exit /b 1
