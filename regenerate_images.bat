@echo off
title Regenerate Cartoonified Images
echo ===================================================
echo  Deleting old changed images and regenerating...
echo ===================================================
echo.
echo 1. Clearing previous cartoonified images...
if exist "Images\Changed" (
    rd /s /q "Images\Changed"
)
echo.
echo 2. Running python generate_ai_difference.py...
python generate_ai_difference.py --force
echo.
echo ===================================================
echo  Regeneration completed successfully!
echo ===================================================
pause
