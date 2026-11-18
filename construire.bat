@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] Interface...
pushd interface & call npm run build & popd
echo [2/3] Application (PyInstaller, quelques minutes)...
".venv\Scripts\pyinstaller.exe" jarvis.spec --noconfirm --log-level WARN || goto :erreur
echo [3/3] Installateur (Inno Setup)...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /Q installateur.iss || goto :erreur
rmdir /s /q build 2>nul
echo.
echo Termine : installateur\ contient JarvisSetup-x.y.z.exe
pause
exit /b 0
:erreur
echo Echec de la construction.
pause
exit /b 1
