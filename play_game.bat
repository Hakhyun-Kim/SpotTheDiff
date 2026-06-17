@echo off
title Spot the Difference Game
echo ===================================================
echo  Starting Spot the Difference Web Game (Flask Server)...
echo  Server Port: 6001
echo ===================================================
echo.
echo Opening Web Browser...
start http://localhost:6001
echo.
echo Starting Flask Server. Close this window to stop the game.
python server.py
