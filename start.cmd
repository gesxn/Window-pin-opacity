@echo off
cd /d "%~dp0"
pyw window_pinner.py
if errorlevel 1 pythonw window_pinner.py

