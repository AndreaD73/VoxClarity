@echo off
rem Double-click entry point / Punto di ingresso con doppio clic. Runs install.ps1 (no admin rights needed).
echo.
echo  VoxClarity - installation / installazione
echo.
set EXTRA=
if defined VOX_NOPAUSE set EXTRA=-NoPrompt
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %EXTRA%
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (
  echo  ==================================================================
  echo   DONE. Start VoxClarity with its icon on your desktop.
  echo   FATTO. Avvia VoxClarity con la sua icona sul desktop.
  echo  ==================================================================
) else (
  echo  ==================================================================
  echo   INSTALLATION FAILED ^(code %RC%^). Read the message above, fix it
  echo   and double-click Installa.bat again.
  echo   INSTALLAZIONE NON RIUSCITA ^(codice %RC%^). Leggi il messaggio qui
  echo   sopra, correggi e fai di nuovo doppio clic su Installa.bat.
  echo  ==================================================================
)
echo.
if not defined VOX_NOPAUSE pause
exit /b %RC%
