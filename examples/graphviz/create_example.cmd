@echo off

REM Example for
REM https://gitlab.com/graphviz/graphviz.git

set "PYTHONEXE=G:\Installed\Python36\python.exe"
set "GRAPHVIZ_BIN_PATH=G:\Installed\Graphviz2.38\bin"
set "PATH=%PATH%;%GRAPHVIZ_BIN_PATH%"

call %PYTHONEXE% ../../src/pdv.py ^
    --sln "../../../others/graphviz/.build/Graphviz.sln" ^
    --dep-item ProjectReference ^
    --with-render ^
    --outfilename graphviz_dependencies.dot ^
    --outdir generated ^
    --ignore-deps run_tests.vcxproj ^
    --ignore-deps uninstall.vcxproj ^
    --ignore-deps ZERO_CHECK.vcxproj ^
    --ignore-deps PACKAGE.vcxproj ^
    --ignore-deps INSTALL.vcxproj ^
    --ignore-deps ALL_BUILD.vcxproj
