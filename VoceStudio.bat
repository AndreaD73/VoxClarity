@echo off
rem Debug launcher with a console (use VoceStudio.vbs for normal use).
"%~dp0.venv\Scripts\python.exe" "%~dp0server.py" %*
