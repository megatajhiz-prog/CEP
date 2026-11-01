@echo off
REM Local Windows build: creates a virtualenv, runs the tests, builds the app and the installer.
REM Requirements: Python 3.11+ on PATH, Inno Setup 6 (https://jrsoftware.org/isinfo.php)
setlocal
cd /d "%~dp0\.."

if not exist .venv ( python -m venv .venv || goto :fail )
call .venv\Scripts\activate.bat || goto :fail
python -m pip install -r requirements-dev.txt || goto :fail

set QT_QPA_PLATFORM=offscreen
python -m pytest -q || goto :fail
set QT_QPA_PLATFORM=

pyinstaller build\CEPWater.spec --noconfirm --distpath dist --workpath build\work || goto :fail

for /f %%v in ('python -c "import waterprofiler;print(waterprofiler.__version__)"') do set VER=%%v

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup 6 not found. The portable app is in dist\CEPWater\
  goto :end
)
%ISCC% /DAppVersion=%VER% build\installer.iss || goto :fail
echo.
echo Installer: Output\CEPWater-Setup-%VER%.exe
goto :end

:fail
echo BUILD FAILED
exit /b 1

:end
endlocal
