@echo off
rem Debug launcher with a console (use VoxClarity.vbs for normal use).
"%~dp0.venv\Scripts\python.exe" "%~dp0server.py" %*
