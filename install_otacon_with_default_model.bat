@echo off
REM Otacon Core + optional Default Model (Ollama + VRAM-tier chat) one-click
REM Designed by Antonio G. Garcia // Otaconskeep
setlocal
title Otacon Installer + Default Model (Windows)

set "OTACON_INSTALL_DEFAULT_MODEL=1"
echo ============================================================
echo  OTACONSKEEP // OTACON + DEFAULT MODEL
echo  Installs Otacon Core and Ollama with a VRAM-sized chat model
echo ============================================================
echo.

call "%~dp0install_otacon.bat"
