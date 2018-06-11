@echo off

REM Example for
REM https://github.com/Microsoft/PTVS

set "PYTHONEXE=G:\Installed\Python36\python.exe"
set "GRAPHVIZ_BIN_PATH=G:\Installed\Graphviz2.38\bin"
set "PATH=%PATH%;%GRAPHVIZ_BIN_PATH%"

call %PYTHONEXE% ../../src/pdv.py ^
    --sln "../../../others/PTVS/Python/PythonTools.sln" ^
    --dep-item ProjectReference ProjectReference2 ^
    --config projects_config.ini ^
    --with-render ^
    --outfilename ptvs_full_dependencies.dot ^
    --outdir generated

call %PYTHONEXE% ../../src/pdv.py ^
    --proj "../../../others/PTVS/Python/Product/Core/Core.csproj" ^
    --dep-item ProjectReference ^
    --with-render ^
    --outfilename ptvs_core_dependencies.dot ^
    --outdir generated

call %PYTHONEXE% ../../src/pdv.py ^
    --sln "../../../others/PTVS/Python/PythonTools.sln" ^
    --dep-item Import ^
    --with-render ^
    --config projects_config.ini ^
    --outfilename ptvs_full_import_dependencies.dot ^
    --outdir generated
