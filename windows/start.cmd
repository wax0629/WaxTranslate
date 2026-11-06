@echo off
setlocal
pushd "%~dp0.." || exit /b 1
if not exist ".venv\Scripts\pythonw.exe" (
    echo Please run windows\setup.cmd first.
    pause
    popd
    exit /b 1
)
start "WaxTranslate" ".venv\Scripts\pythonw.exe" "windows\app.py"
popd
