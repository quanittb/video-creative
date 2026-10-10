@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0"
set "PYTHONUTF8=1"
if defined VCS_ECHO_CONTROLLER_PYTHON (
  "%VCS_ECHO_CONTROLLER_PYTHON%" "scripts\echo_flash_windows.py" %*
) else (
  python "scripts\echo_flash_windows.py" %*
)
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
