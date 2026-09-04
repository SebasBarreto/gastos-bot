@echo off
REM ============================================================
REM   Arranca el bot de gastos (Telegram -> Notion)
REM ============================================================
cd /d "%~dp0"

REM Instala dependencias la primera vez (requests + dotenv)
python -m pip install --quiet requests python-dotenv

echo Arrancando el bot de gastos... (cierra esta ventana para pararlo)
python gastos_bot.py
pause
