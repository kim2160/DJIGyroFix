@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3.12 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 exit /b 1
)

set "APP_PYTHON=.venv\Scripts\python.exe"
"%APP_PYTHON%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  "%APP_PYTHON%" -m pip install --disable-pip-version-check -r requirements-build.txt
  if errorlevel 1 exit /b 1
)

"%APP_PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --version-file packaging\windows_version_info.txt ^
  --name DJI_Gyro_Fix ^
  --distpath dist ^
  --workpath build ^
  app.py
if errorlevel 1 exit /b 1

copy /Y "docs\사용방법.txt" "dist\사용방법.txt" >nul
echo Built: %CD%\dist\DJI_Gyro_Fix.exe
endlocal
