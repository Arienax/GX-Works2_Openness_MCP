@echo off
setlocal EnableExtensions

chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "REQ=requirements.txt"
set "IS_WIN7="

ver | findstr /C:"6.1." >nul 2>&1
if not errorlevel 1 (
    set "REQ=requirements-win7.txt"
    set "IS_WIN7=1"
)

echo ==============================================
echo   GX Works2 Openness MCP - Setup ^& Start
echo ==============================================
echo.

if not exist "%REQ%" (
    echo [ERROR] Cannot find %REQ%.
    echo Please run this script from the repository root.
    goto :fail
)

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python 3 was not found.
    echo Install Python first, then run start.bat again.
    echo Recommended: Python 3.11+ on Windows 10/11.
    echo Windows 7 should use Python 3.8 and requirements-win7.txt.
    goto :fail
)

for /f "delims=" %%V in ('%PYTHON_CMD% -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"') do set "PYTHON_VERSION=%%V"
echo [INFO] Python: %PYTHON_VERSION%
echo [INFO] Requirements: %REQ%

if defined IS_WIN7 (
    %PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)"
    if errorlevel 1 (
        echo [ERROR] Windows 7 requires Python 3.8 or newer compatible Python.
        goto :fail
    )
) else (
    %PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
    if errorlevel 1 (
        echo [ERROR] The current requirements need Python 3.11 or newer.
        echo Please install Python 3.11+ and run this script again.
        goto :fail
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [1/3] Creating virtual environment .venv ...
    %PYTHON_CMD% -m venv ".venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        goto :fail
    )
) else (
    echo.
    echo [1/3] Reusing existing virtual environment .venv
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if defined IS_WIN7 (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
) else (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
)
if errorlevel 1 (
    echo [ERROR] Existing .venv uses an incompatible Python version.
    echo Delete the .venv folder and run start.bat again.
    goto :fail
)

"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] pip is missing; installing pip ...
    "%VENV_PY%" -m ensurepip --upgrade
    if errorlevel 1 (
        echo [ERROR] Failed to install pip.
        goto :fail
    )
)

echo.
echo [2/3] Installing / updating dependencies ...
"%VENV_PY%" -m pip install -r "%REQ%"
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo Check your network connection and the pip error above.
    goto :fail
)

echo.
echo [3/3] Starting PLC AI Workbench ...
echo.
"%VENV_PY%" "src\main.py"
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo [ERROR] Application exited with code %APP_EXIT%.
    goto :fail
)

endlocal
exit /b 0

:fail
echo.
echo Press any key to close this window...
pause >nul
endlocal
exit /b 1
