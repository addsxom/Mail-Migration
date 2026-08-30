@echo off
setlocal
cd /d "%~dp0"

title Mail Migration

set "PYTHON=.venv\Scripts\python.exe"

cls
echo.
echo  ========================================
echo           MAIL MIGRATION
echo  ========================================
echo.

if not exist "%PYTHON%" (
    echo  Configuration de l'environnement...
    echo.
    py -m venv .venv

    if errorlevel 1 (
        echo.
        echo  [ERREUR] Impossible de creer l'environnement Python.
        echo  Verifiez que Python est correctement installe.
        echo.
        pause
        exit /b 1
    )
)

echo  Dependances
"%PYTHON%" -m pip install --upgrade pip --disable-pip-version-check -q
if errorlevel 1 goto :pip_error

"%PYTHON%" -m pip install -r requirements.txt --disable-pip-version-check -q
if errorlevel 1 goto :deps_error

echo  Pret.
echo.
echo  Lancement de Mail Migration...
echo.

"%PYTHON%" main.py
set "EXIT_CODE=%errorlevel%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo  [ERREUR] Mail Migration s'est arretee avec une erreur.
    echo  Code : %EXIT_CODE%
    echo.
    pause
)

endlocal
exit /b %EXIT_CODE%

:pip_error
echo.
echo  [ERREUR] Impossible de preparer les dependances.
echo.
pause
endlocal
exit /b 1

:deps_error
echo.
echo  [ERREUR] Impossible d'installer les dependances.
echo.
pause
endlocal
exit /b 1
