@echo off
cd /d "%~dp0"
python check_kobo.py
echo.
streamlit run app.py
pause
