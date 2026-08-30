@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Mail Migration

set "PYTHON=.venv\Scripts\python.exe"

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
goto :launch

:install_deps
powershell -NoProfile -ExecutionPolicy Bypass -Command "$py=Join-Path (Get-Location) '.venv\Scripts\python.exe'; $p=Start-Process -FilePath $py -ArgumentList @('-m','pip','install','-r','requirements.txt','--disable-pip-version-check','-q') -WorkingDirectory (Get-Location) -PassThru -WindowStyle Hidden; $chars='|','/','-','\\'; $i=0; while(-not $p.HasExited){ Write-Host -NoNewline ([char]13 + ' [2/3] Dependances              Installation... ' + $chars[$i %% 4]); $i++; Start-Sleep -Milliseconds 120; $p.Refresh() }; $code=$p.ExitCode; Write-Host ([char]13 + (' ' * 75) + [char]13); exit $code"
if errorlevel 1 goto :deps_error
echo  [2/3] Dependances              OK

:launch
echo  [3/3] Mail Migration           Demarrage...
echo.
"%PYTHON%" main.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto :app_error

endlocal
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
echo  [ERREUR] Impossible d'installer les dependances.
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
