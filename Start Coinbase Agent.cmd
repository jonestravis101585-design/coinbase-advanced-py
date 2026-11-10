@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1

where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 "%~dp0scripts\start_coinbase_agent.py" %*
goto finished

:use_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python "%~dp0scripts\start_coinbase_agent.py" %*
goto finished

:no_python
echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
echo Then reopen this launcher. No administrator permissions are needed by this launcher.
if "%~1"=="" pause
exit /b 1

:finished
set "agentExitCode=%errorlevel%"
if "%~1"=="" pause
exit /b %agentExitCode%
