@echo off
setlocal
cd /d %~dp0\..

python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

python scripts\write_build_config.py
pyinstaller --noconfirm --clean FlashFoodPrintAgent.spec

echo Build listo.
pause
