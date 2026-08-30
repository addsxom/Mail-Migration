@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Mail Migration

set "PYTHON=.venv\Scripts\python.exe"
set "START_TIME=%TIME%"

cls
echo.
echo  ========================================
echo            MAIL MIGRATION
echo  ========================================
echo.
echo  Preparation de l'application...
echo.

if not exist "%PYTHON%" (
    echo  [1/3] Environnement Python    Creation...
    py -m venv .venv
    if errorlevel 1 goto :venv_error
) else (
    echo  [1/3] Environnement Python    OK
)

"%PYTHON%" -c "import importlib.util,sys; mods=['PySide6','sqlalchemy','googleapiclient','reportlab']; sys.exit(1 if any(importlib.util.find_spec(m) is None for m in mods) else 0)" >nul 2>&1
if errorlevel 1 goto :install_deps

echo  [2/3] Dependances              OK
call :elapsed
goto :launch

:install_deps
echo  [2/3] Dependances              Installation...
"%PYTHON%" -m pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 goto :deps_error
echo  [2/3] Dependances              OK
call :elapsed

:launch
echo  [3/3] Mail Migration           Demarrage...
echo.
"%PYTHON%" main.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto :app_error

endlocal
exit /b 0

:elapsed
set "END_TIME=%TIME%"
for /f "tokens=1-4 delims=:,." %%a in ("%START_TIME%") do set /a "S1=%%a*360000+%%b*6000+%%c*100+%%d"
for /f "tokens=1-4 delims=:,." %%a in ("%END_TIME%") do set /a "S2=%%a*360000+%%b*6000+%%c*100+%%d"
set /a "ELAPSED=(S2-S1)/100"
if !ELAPSED! lss 0 set /a "ELAPSED+=86400"
echo  Temps de preparation : !ELAPSED! seconde(s)
echo.
exit /b 0

:venv_error
echo.
echo  [ERREUR] Impossible de creer l'environnement Python.
echo  Verifiez que Python est installe correctement.
echo.
pause
endlocal
exit /b 1

:deps_error
echo.
echo  [ERREUR] Dependances indisponibles.
echo  Verifiez votre connexion Internet puis relancez l'application.
echo.
pause
endlocal
exit /b 1

:app_error
echo.
echo  ========================================
echo       MAIL MIGRATION - ERREUR
echo  ========================================
echo.
echo  Code de sortie : %EXIT_CODE%
echo.
pause
endlocal
exit /b %EXIT_CODE%
