@echo off
rem Clique duas vezes (ou use o atalho) para abrir o Fatura OCR.
rem "& exit /b" na mesma linha: a atualizacao pode trocar este arquivo enquanto ele roda.
title Fatura OCR
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1" %* & exit /b
