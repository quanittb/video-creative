@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0"
set "PYTHONUTF8=1"
set "PYTHON_CMD=python"
if defined VCS_PYTHON set "PYTHON_CMD=%VCS_PYTHON%"
"%PYTHON_CMD%" -u "scripts\test_vertical_ads.py" %*
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
