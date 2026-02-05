@echo off
setlocal
set "REPO_ROOT=%~dp0"
powershell -ExecutionPolicy Bypass -File "%REPO_ROOT%run.ps1" %*
