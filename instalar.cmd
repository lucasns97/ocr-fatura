@echo off
rem Clique duas vezes para instalar ou atualizar o Fatura OCR.
rem Tudo numa linha so: o instalador pode substituir este arquivo enquanto ele roda.
title Instalador - Fatura OCR
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" & echo. & pause
