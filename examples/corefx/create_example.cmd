@echo off

REM Example for
REM https://github.com/dotnet/corefx

set "PYTHONEXE=G:\Installed\Python36\python.exe"
set "GRAPHVIZ_BIN_PATH=G:\Installed\Graphviz2.38\bin"
set "PATH=%PATH%;%GRAPHVIZ_BIN_PATH%"

call %PYTHONEXE% ../../src/pdv.py ^
    --sln "../../../others/corefx/src/System.Data.Common/System.Data.Common.sln" ^
    --dep-item ProjectReference ^
    --with-render ^
    --outfilename corefx_common_dependencies.dot ^
    --outdir generated ^
    --config projects_config.ini

call %PYTHONEXE% ../../src/pdv.py ^
    --proj "../../../others/corefx/src/System.Net.WebSockets/ref/System.Net.WebSockets.csproj" ^
    --dep-item ProjectReference ^
    --with-render ^
    --outfilename corefx_websockets_dependencies.dot ^
    --outdir generated
