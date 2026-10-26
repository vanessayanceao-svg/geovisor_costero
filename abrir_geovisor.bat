@echo off
REM Abre el geovisor costero en el navegador (entorno conda "coastsat").
REM Si su entorno tiene otro nombre, cambie la linea "call conda activate coastsat".
cd /d "%~dp0"
call conda activate coastsat 2>nul
if errorlevel 1 (
  echo No se pudo activar el entorno conda "coastsat". Abra Anaconda Prompt, active su entorno y ejecute:
  echo     streamlit run app.py
  pause
  exit /b 1
)
python scripts\comprobar_entorno.py
echo.
echo Iniciando el geovisor (cierre esta ventana para detenerlo)...
streamlit run app.py
pause
