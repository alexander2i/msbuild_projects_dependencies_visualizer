# msbuild_projects_dependencies_visualizer
This project is a simple python script which allows to visualize dependencies for a MSBuild projects.

The result of the script execution is a simple *.gv file. Which can be rendered with the [graphviz](https://www.graphviz.org/) utilities like dot.exe. Using command line parameter `--with-render` the script can automatically call specified (default: dot.exe) graphviz utility after generation *.gv file.

## Examples
TODO: Insert images

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
```cmd
python pdv.py --sln=path_to_sln_file --dtype=XPROJ --outfilename=dependenices.gv --with-render
```
or
```cmd
python pdv.py --proj=path_to_proj_file_1 --proj=path_to_proj_file_2 --dtype=PROPS --outfilename=dependenices.gv --with-render
```
