@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Mail Migration
set "PYTHON=.venv\Scripts\python.exe"

cls
for /f "tokens=*" %%A in ('powershell -NoProfile -Command "Write-Host ([char]27 + '[96m')"') do echo %%A

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                                                              ║
echo  ║                      MAIL MIGRATION                         ║
echo  ║              Gmail account migration assistant              ║
echo  ║                                                              ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.
echo  ────────────────────────────────────────────────────────────────
echo   PREPARATION
echo  ────────────────────────────────────────────────────────────────
echo.

if not exist "%PYTHON%" (
    <nul set /p "=  [1/3]  Python       Creation de l'environnement... "
    py -m venv .venv >nul 2>&1
    if errorlevel 1 goto :venv_error
    echo  OK
) else (
    echo  [1/3]  Python       ✓ Environnement pret
)

"%PYTHON%" -c "import importlib.util,sys; mods=['PySide6','sqlalchemy','googleapiclient','reportlab']; sys.exit(1 if any(importlib.util.find_spec(m) is None for m in mods) else 0)" >nul 2>&1
if errorlevel 1 goto :install_deps

echo  [2/3]  Dependances  ✓ Toutes les dependances sont presentes
goto :launch

:install_deps
<nul set /p "=  [2/3]  Dependances  Installation "
powershell -NoProfile -ExecutionPolicy Bypass -Command "$py=Join-Path (Get-Location) '.venv\Scripts\python.exe'; $args=@('-m','pip','install','-r','requirements.txt','--disable-pip-version-check','-q'); $p=Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory (Get-Location) -PassThru -WindowStyle Hidden; $chars=@('|','/','-','\'); $i=0; while(-not $p.HasExited){ $p.Refresh(); Write-Host -NoNewline ([char]8 + $chars[$i %% 4]); $i++; Start-Sleep -Milliseconds 120 }; $p.WaitForExit(); exit $p.ExitCode"
if errorlevel 1 goto :deps_error
echo  ✓

:launch
echo.
echo  ────────────────────────────────────────────────────────────────
echo   LANCEMENT
echo  ────────────────────────────────────────────────────────────────
echo.
echo  [3/3]  Application  ✓ Demarrage de Mail Migration...
echo.
"%PYTHON%" main.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto :app_error

endlocal
exit /b 0

:venv_error
call :error_box "Impossible de creer l'environnement Python."
endlocal
exit /b 1

:deps_error
call :error_box "Impossible d'installer les dependances."
endlocal
exit /b 1

:app_error
echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                       ERREUR                                 ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║  Mail Migration s'est arretee.                              ║
echo  ║  Code de sortie : %EXIT_CODE%                                      ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.
pause
endlocal
exit /b %EXIT_CODE%

:error_box
echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                       ERREUR                                 ║
echo  ╠══════════════════════════════════════════════════════════════╣
echo  ║  %~1

echo  ╚══════════════════════════════════════════════════════════════╝
echo.
pause
exit /b
