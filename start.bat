@echo off
setlocal
cd /d "%~dp0"
title Mail Migration

set "PYTHON=.venv\Scripts\python.exe"

cls
echo.
echo  ========================================
echo             MAIL MIGRATION
echo       Gmail Migration Assistant
echo  ========================================
echo.

REM --- Python environment ---
echo [1/3] Verification de Python...

if not exist "%PYTHON%" (
    echo       Creation de l'environnement virtuel...
    py -m venv .venv
    if errorlevel 1 goto :error_venv
    echo       OK
) else (
    echo       Environnement virtuel deja present.
)

echo.
echo [2/3] Verification des dependances...
"%PYTHON%" -m pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 goto :error_deps
echo       OK

echo.
echo [3/3] Lancement de Mail Migration...
echo.

"%PYTHON%" main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" goto :error_app

endlocal
exit /b 0

:error_venv
echo.
echo [ERREUR] Impossible de creer l'environnement Python.
echo Verifiez que Python est installe et accessible avec la commande ^"py^".
echo.
pause
endlocal
exit /b 1

:error_deps
echo.
echo [ERREUR] Impossible d'installer les dependances.
echo Verifiez votre connexion Internet et le fichier requirements.txt.
echo.
pause
endlocal
exit /b 1

:error_app
echo.
echo ========================================
echo [ERREUR] Mail Migration s'est arrete.
echo Code de sortie : %EXIT_CODE%
echo ========================================
echo.
pause
endlocal
exit /b %EXIT_CODE%
