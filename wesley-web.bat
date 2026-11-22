@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "wesley\static\index.html" (
  echo Compilation de l'interface...
  pushd interface
  if not exist node_modules call npm install
  call npm run build
  popd
)
".venv\Scripts\python.exe" -m wesley.web %*
