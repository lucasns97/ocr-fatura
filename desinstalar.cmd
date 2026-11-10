@echo off
rem Clique duas vezes para remover o Fatura OCR e os atalhos.
title Desinstalar - Fatura OCR
cd /d "%TEMP%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1" & echo. & pause
