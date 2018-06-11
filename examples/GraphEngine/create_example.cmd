@echo off

REM Example for
REM https://github.com/Microsoft/GraphEngine

set "PYTHONEXE=G:\Installed\Python36\python.exe"
set "GRAPHVIZ_BIN_PATH=G:\Installed\Graphviz2.38\bin"
set "PATH=%PATH%;%GRAPHVIZ_BIN_PATH%"

call %PYTHONEXE% ../../sources/pdv.py ^
    --sln "../../../others/GraphEngine/src/Modules/Trinity.FFI/Trinity.FFI.sln" ^
    --dep-item ProjectReference ^
    --with-render ^
    --outfilename graphengine_trinityffi_dependencies.dot ^
    --outdir generated
