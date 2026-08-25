@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Nordex Comparador - gerador do executavel
echo ============================================================
echo.

set "PYTHON="

REM ------------------------------------------------------------
REM 1) Caminho passado na linha de comando:
REM       build_exe.bat "C:\...\python\python.exe"
REM ------------------------------------------------------------
if not "%~1"=="" (
    if exist "%~1" (
        set "PYTHON=%~1"
        goto :achou
    )
    echo [aviso] O caminho informado nao existe: %~1
    echo.
)

REM ------------------------------------------------------------
REM 2) Descobrir a Area de Trabalho real. Em maquina corporativa
REM    ela costuma estar redirecionada pro OneDrive, entao nao da
REM    pra confiar em %USERPROFILE%\Desktop.
REM ------------------------------------------------------------
set "DESKTOP=%USERPROFILE%\Desktop"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul') do call set "DESKTOP=%%B"

REM ------------------------------------------------------------
REM 3) Locais conhecidos. O WinPython guarda o interpretador em
REM    <raiz>\python\python.exe, e a pasta raiz pode se chamar
REM    "Python", "WPy64-<versao>", etc.
REM ------------------------------------------------------------
call :testar "%DESKTOP%\Python\python\python.exe"
if defined PYTHON goto :achou
call :testar "%USERPROFILE%\Desktop\Python\python\python.exe"
if defined PYTHON goto :achou
call :testar "%USERPROFILE%\Python\python\python.exe"
if defined PYTHON goto :achou
if defined OneDrive call :testar "%OneDrive%\Desktop\Python\python\python.exe"
if defined PYTHON goto :achou
if defined OneDriveCommercial call :testar "%OneDriveCommercial%\Desktop\Python\python\python.exe"
if defined PYTHON goto :achou

REM ------------------------------------------------------------
REM 4) Varrer pastas que comecem com WPy* ou Python* nos lugares
REM    mais provaveis, inclusive uma pasta acima desta (caso o app
REM    tenha sido colocado dentro da propria pasta do WinPython).
REM ------------------------------------------------------------
call :varrer "%DESKTOP%"
if defined PYTHON goto :achou
call :varrer "%USERPROFILE%\Desktop"
if defined PYTHON goto :achou
call :varrer "%USERPROFILE%"
if defined PYTHON goto :achou
if defined OneDrive call :varrer "%OneDrive%\Desktop"
if defined PYTHON goto :achou
call :varrer "%~dp0.."
if defined PYTHON goto :achou
call :varrer "%~dp0..\.."
if defined PYTHON goto :achou
call :varrer "C:\"
if defined PYTHON goto :achou

REM ------------------------------------------------------------
REM 5) Ultimo recurso: o que estiver no PATH.
REM ------------------------------------------------------------
for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYTHON set "PYTHON=%%P"
)
if defined PYTHON goto :achou
for /f "delims=" %%P in ('where python3 2^>nul') do (
    if not defined PYTHON set "PYTHON=%%P"
)
if defined PYTHON goto :achou

goto :naoachou


REM ============ subrotinas ============

:testar
if defined PYTHON goto :eof
if exist "%~1" set "PYTHON=%~1"
goto :eof

:varrer
if defined PYTHON goto :eof
if not exist "%~1" goto :eof
for /d %%D in ("%~1\WPy*") do (
    if not defined PYTHON if exist "%%D\python\python.exe" set "PYTHON=%%D\python\python.exe"
)
for /d %%D in ("%~1\Python*") do (
    if not defined PYTHON if exist "%%D\python\python.exe" set "PYTHON=%%D\python\python.exe"
)
for /d %%D in ("%~1\WinPython*") do (
    if not defined PYTHON if exist "%%D\python\python.exe" set "PYTHON=%%D\python\python.exe"
)
goto :eof


:naoachou
echo Nao consegui localizar o python.exe automaticamente.
echo.
echo Procurei em:
echo    "%DESKTOP%\Python\python\python.exe"
echo    "%USERPROFILE%\Python\python\python.exe"
echo    pastas WPy* / Python* / WinPython* na Area de Trabalho e no perfil
echo    e tambem no PATH do sistema
echo.
echo SOLUCAO: passe o caminho do python.exe direto pra este script.
echo No seu caso ele deve estar em algo como:
echo.
echo    "%DESKTOP%\Python\python\python.exe"
echo.
echo Abra o Prompt de Comando nesta pasta e rode:
echo.
echo    build_exe.bat "%DESKTOP%\Python\python\python.exe"
echo.
echo (ajuste o caminho se a pasta do WinPython estiver em outro lugar -
echo  o que importa e apontar pro python.exe de dentro dela)
echo.
pause
exit /b 1


:achou
echo Python encontrado em:
echo    "%PYTHON%"
"%PYTHON%" --version
if errorlevel 1 (
    echo.
    echo [erro] Esse arquivo nao respondeu como um interpretador Python valido.
    pause
    exit /b 1
)
echo.

echo ------------------------------------------------------------
echo  Instalando dependencias ^(pandas, openpyxl, pyinstaller^)...
echo ------------------------------------------------------------
"%PYTHON%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :erro

echo.
echo ------------------------------------------------------------
echo  Gerando o executavel... ^(demora alguns minutos^)
echo ------------------------------------------------------------
"%PYTHON%" -m PyInstaller --noconfirm --onefile --windowed ^
    --name "NordexComparador" ^
    --add-data "assets;assets" ^
    --collect-all pandas ^
    --collect-all openpyxl ^
    gui.py
if errorlevel 1 goto :erro

echo.
echo ============================================================
echo  PRONTO: dist\NordexComparador.exe
echo ============================================================
echo  Esse .exe pode ser copiado e usado em qualquer PC Windows,
echo  sem precisar de Python instalado la.
echo.
pause
exit /b 0


:erro
echo.
echo ============================================================
echo  FALHOU - veja a mensagem de erro acima.
echo ============================================================
pause
exit /b 1
