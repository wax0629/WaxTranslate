@echo off
setlocal
pushd "%~dp0.." || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv || goto failed
)
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m ensurepip || goto failed
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r windows\requirements.txt || goto failed
".venv\Scripts\python.exe" windows\install_model.py || goto failed
echo Ready. Launch windows\start.cmd to open WaxTranslate.
popd
exit /b 0
:failed
echo Setup failed. Check the output above, Python 3.12 x64, and your network.
popd
exit /b 1
