@echo off

set PYTHONPATH=%PYTHONPATH%;../sources/
set PYTHONEXE=G:\Installed\Python36\python.exe

call %PYTHONEXE% traverse_for_projects.py %*
