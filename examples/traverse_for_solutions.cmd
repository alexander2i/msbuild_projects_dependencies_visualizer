@echo off

set PYTHONPATH=%PYTHONPATH%;../src/
set PYTHONEXE=G:\Installed\Python36\python.exe

call %PYTHONEXE% traverse_for_solutions.py %*
