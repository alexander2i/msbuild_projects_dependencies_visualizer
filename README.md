# msbuild_projects_dependencies_visualizer
This project is a simple python script which allows to visualize dependencies for a MSBuild projects and solutions.

The result of the script execution is a simple *.gv file. Which can be rendered with the [graphviz](https://www.graphviz.org/) utilities like dot.exe. Using command line parameter `--with-render` the script can automatically call specified (default: dot.exe) graphviz utility after generation *.gv file.

## Examples
![https://github.com/Microsoft/PTVS](examples\PTVS\generated\ptvs_full_dependencies.dot.svg)

## Features
* Building dependencies for a solution (option: `--sln`)
* Building dependencies for a particular project (option: `--proj`).
* Supported any MSBuild projects (*.vcxproj, *.csproj, *.vbproj, ...)

You can specify several projects or solutions at the same time to view dependencies in one image.

## Requirements
* Python 3.4+
* Installed [graphviz module](https://pypi.org/project/graphviz/) for the Python
* Installed [graphviz packet](https://www.graphviz.org/) if you want to render the image with a projects dependencies 

## How to use

1. Use help
```cmd
python3 pdv.py --help
```
2. Find and print dependencies for all projects in the solution
```cmd
python3 pdv.py ^
    --sln FilePathToSolution ^
    --dep-item ProjectReference ^
    --with-render ^
    --outfilename dependencies.dot
```
3. Find and print 'Import' dependencies for the Project1 and Project2
```cmd
python3 pdv.py ^
    --proj filepath_to_project1 ^
    --proj filepath_to_project2 ^
    --dep-item Import ^
    --with-render ^
    --outfilename p1_p2_imports.dot
```

See detailed examples in `examples`.
