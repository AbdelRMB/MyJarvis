@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] Interface...
pushd interface & call npm run build & popd
echo [2/3] Application (PyInstaller, quelques minutes)...
".venv\Scripts\pyinstaller.exe" jarvis.spec --noconfirm --log-level WARN || goto :erreur
echo [3/3] Installateur (Inno Setup)...
for /f "delims=" %%v in ('".venv\Scripts\python.exe" -c "from jarvis.version import VERSION; print(VERSION)"') do set VERSION=%%v
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /Q /DVersion=%VERSION% installateur.iss || goto :erreur
rmdir /s /q build 2>nul
echo.
echo Termine : installateur\ contient JarvisSetup-x.y.z.exe
if not defined SANS_PAUSE pause
exit /b 0
:erreur
echo Echec de la construction.
if not defined SANS_PAUSE pause
exit /b 1
