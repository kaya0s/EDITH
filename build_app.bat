@echo off
title JARVIS Build Process
color 0B

echo ========================================
echo Building JARVIS Standalone Application
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then run: .venv\Scripts\activate
    echo Then run: pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/4] Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check if activation was successful
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment!
    pause
    exit /b 1
)

REM Install PyInstaller if not already installed
echo [2/4] Checking PyInstaller installation...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Create build directory if it doesn't exist
if not exist "build" (
    mkdir build
)

REM Clean previous builds
echo [3/4] Cleaning previous builds...
if exist "dist" (
    rmdir /s /q "dist"
)
if exist "build\JARVIS" (
    rmdir /s /q "build\JARVIS"
)

REM Build the executable
echo [4/4] Building standalone executable...
pyinstaller build/jarvis.spec --clean --noconfirm

REM Check if build was successful
if exist "dist\JARVIS.exe" (
    echo.
    echo ========================================
    echo BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Executable created: dist\JARVIS.exe
    echo.
    echo To run JARVIS:
    echo   1. Copy dist\JARVIS.exe to your desired location
    echo   2. Create a .env file with your API keys
    echo   3. Run JARVIS.exe
    echo.
    echo Note: The first run may take longer as it extracts dependencies.
) else (
    echo.
    echo [ERROR] Build failed! Check the output above for errors.
    pause
    exit /b 1
)

echo.
pause
