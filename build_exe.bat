@echo off
setlocal
cd /d %~dp0
if not exist venv (
  py -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name "SAIN DTF Print Engine" --add-data "sample_output;sample_output" main.py
endlocal
