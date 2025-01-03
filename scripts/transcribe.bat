@echo off
set /p link="Enter Instagram Reel URL: "

:: Get the root project directory (one level up from scripts folder)
set "PROJECT_DIR=%~dp0.."
set timestamp=%date:~-4%-%date:~4,2%-%date:~7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%
set "TEMP_DIR=%USERPROFILE%\Downloads\%timestamp%"

:: Create temp directory
mkdir "%TEMP_DIR%"

:: Activate virtual environment (now looking for .venv instead of venv)
if exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
) else (
    echo Virtual environment not found. Please run:
    echo python -m venv .venv
    echo .\.venv\Scripts\activate
    echo pip install -r requirements.txt
    exit /b 1
)

:: Add project root to PYTHONPATH
set PYTHONPATH=%PROJECT_DIR%;%PYTHONPATH%

:: Run the transcription script
python -m src.cli.main %link% %* --temp-dir "%TEMP_DIR%"

:: Cleanup
rmdir /s /q "%TEMP_DIR%"

:: Pause to show any errors
pause