@echo off
title Spot the Difference Game
echo ===================================================
echo  Starting Spot the Difference Web Game...
echo  Server Port: 8000
echo ===================================================
echo.
echo Opening Web Browser...
start http://localhost:8000
echo.
echo Starting Web Server. Close this window to stop the game.
python -m http.server 8000
