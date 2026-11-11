@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Consulte COMO_USAR_INTERFACE.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "fisio_web.py"
if errorlevel 1 (
  echo Nao foi possivel iniciar o Fisio. Veja a mensagem acima.
  pause
)
