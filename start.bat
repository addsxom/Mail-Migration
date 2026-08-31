@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Mail Migration
set "PYTHON=.venv\Scripts\python.exe"

cls
echo.
echo  ================================================================
echo                         MAIL MIGRATION
echo                    Gmail Migration Assistant
echo  ================================================================
echo.
echo  Preparation de l'application...
echo.

if not exist "%PYTHON%" (
    <nul set /p "=  [1/3]  Python       Creation de l'environnement... "
    py -m venv .venv >nul 2>&1
    if errorlevel 1 goto :venv_error
    echo OK
) else (
    echo  [1/3]  Python       Environnement pret
)

"%PYTHON%" -c "import importlib.util,sys; mods=['PySide6','sqlalchemy','googleapiclient','reportlab']; sys.exit(1 if any(importlib.util.find_spec(m) is None for m in mods) else 0)" >nul 2>&1
if errorlevel 1 goto :install_deps

echo  [2/3]  Dependances  Dependances deja installees
goto :launch

:install_deps
<nul set /p "=  [2/3]  Dependances  Installation "
powershell -NoProfile -ExecutionPolicy Bypass -Command "$py=Join-Path (Get-Location) '.venv\Scripts\python.exe'; $args=@('-m','pip','install','-r','requirements.txt','--disable-pip-version-check','-q'); $p=Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory (Get-Location) -PassThru -WindowStyle Hidden; $chars=@('|','/','-','\'); $i=0; while(-not $p.HasExited){ $p.Refresh(); Write-Host -NoNewline ([char]13 + '  [2/3]  Dependances  Installation ' + $chars[$i %% 4] + '   '); $i++; Start-Sleep -Milliseconds 120 }; $p.WaitForExit(); exit $p.ExitCode"
if errorlevel 1 goto :deps_error
echo  [2/3]  Dependances  Installation terminee

:launch
echo.
echo  ----------------------------------------------------------------
echo  [3/3]  Application   Demarrage de Mail Migration...
echo  ----------------------------------------------------------------
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
echo  ================================================================
echo                         MAIL MIGRATION
echo  ================================================================
echo.
echo  ERREUR : l'application s'est arretee.
echo  Code de sortie : %EXIT_CODE%
echo.
pause
endlocal
exit /b %EXIT_CODE%
