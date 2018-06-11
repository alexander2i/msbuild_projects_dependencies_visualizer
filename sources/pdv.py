import os
import sys
import pathlib
# TODO: consider using xml.etree.ElementTree
import xml.dom
import xml.dom.minidom as minidom
import enum
import argparse
import configparser
import re
import logging
import time

import graphviz


# projects config is intended to resolve variables in the projects paths
_global_projects_config = configparser.ConfigParser()


def get_attribute_values(dom, tag, attribute, masks):
    '''Returns a list of found values of attributes under the given tag
       that matches any of masks'''

    if dom is None:
        return None

    values = []

    tag_nodes = dom.getElementsByTagName(tag)
    for tag_node in tag_nodes:
        if tag_node.hasAttribute(attribute):
            # TODO: values may be found with a condition
            # Example: <Import Project="$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props" Condition="exists('$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props')" Label="LocalAppDataPlatform" />
            # so we should take into account this case
            value = tag_node.getAttribute(attribute)
            if not masks:
                # allow any dependency
                values.append(value)
            else:
                # search for matches under mask
                for mask in masks:
                    if value.lower().endswith(mask):
                        values.append(value)
                        break

    return values

class MSBuildItems(enum.Enum):
    ITEM_PROJECT_REF = 'ProjectReference'
    ITEM_PROJECT_REF2 = 'ProjectReference2'
    ITEM_IMPORT = 'Import'

    def get_attribute(self):
        return {MSBuildItems.ITEM_PROJECT_REF: 'Include',
                MSBuildItems.ITEM_PROJECT_REF2: 'Include',
                MSBuildItems.ITEM_IMPORT: 'Project'
               }[self]

    def get_dependencies(self, project_dom, masks):
        '''Returns a list of found values of the corresponding attribute under self.value tag'''
        return get_attribute_values(project_dom, self.value, self.get_attribute(), masks)


class MSBuildItemDependencyInfo():
    def __init__(self, item_name, masks):
        self.item = MSBuildItems(item_name)
        self.dependencies_masks =\
            [mask.lower() for mask in masks] if masks else None


# TODO: sometimes variables may contain another variables within yourself
# Need consider this case
def get_string_variables(string):
    return re.findall(r'\$\(.+?\)', string)


def try_resolve_variables(string_to_resolve):
    '''Search for variable in _global_projects_config['DEFAULT'] and replace if it found'''
    result = string_to_resolve

    # TODO: consider using project's own section in the config for its own variables
    def_section = _global_projects_config['DEFAULT']
    variables = get_string_variables(string_to_resolve)
    for var in variables:
        if var in def_section and \
                def_section[var]:
            result = result.replace(var, def_section[var])

    return result

def is_standard_project(project_filepath):
    # TODO: extend this list and/or use config for a projects to be ignored
    standard_projects = ['Microsoft.Cpp.props',
                         'Microsoft.Cpp.Default.props',
                         'Microsoft.Cpp.$(Platform).user.props']
    for proj in standard_projects:
        if project_filepath.endswith(proj):
            return True

    return False

class MSBuildXmlProject:
    '''Instance of this class is any MSBuld project like "*proj" or "*.props" or "*.targets" file'''
    def __init__(self, project_file_path, dependenies_info):
        self.file_path = project_file_path
        self.dependenies_info = dependenies_info
        self.proj_dependencies = set()
        self._dom = None
        self._number = None

    def __str__(self):
        return 'Project [{}]'.format(self.file_path)

    def __hash__(self):
        return hash(self.file_path.lower())

    def __eq__(self, other):
        return self.file_path.lower() == other.file_path.lower()

    def __lt__(self, other):
        return self.file_path.lower() < other.file_path.lower()

    def _add_project_dependency(self, project):
        if project in self.proj_dependencies:
            logging.info('Project [%s] already present as dependency for [%s]',
                         project.get_project_filepath(),
                         self.get_project_filepath())
            return

        self.proj_dependencies.add(project)

    def _get_project_dom(self):
        if self._dom is None:
            if not self.is_project_exists():
                logging.warning("Failed to parse xml. File [%s] not found.", self.file_path)
                return None

            try:
                self._dom = minidom.parse(self.file_path)
            except:
                logging.error('Failed to parse project [%s].', self.file_path)
                return None

        return self._dom

    def is_project_exists(self):
        return os.path.isfile(self.file_path)

    def _get_project_abs_path(self, project_path):
        if os.path.isabs(project_path):
            return os.path.normpath(project_path)

        # Here project_path may be relative to the current project dir
        this_project_dir = os.path.dirname(self.file_path)
        project_path_abs = os.path.join(this_project_dir, project_path)
        if os.path.isfile(project_path_abs):
            return os.path.normpath(project_path_abs)

        # Here project_path may contain visual studio variables in the path.
        # For example $(SolutionDir), $(VCTargetsPath) etc.
        resolved_path = try_resolve_variables(project_path)

        if os.path.isfile(resolved_path):
            return os.path.abspath(resolved_path)

        # some variables may not have been resolved
        return project_path

    def get_project_filepath(self):
        return self.file_path

    def get_project_filename(self):
        return os.path.basename(self.file_path)

    def get_project_directory(self):
        return os.path.dirname(self.file_path)

    def get_project_dependencies(self):
        return self.proj_dependencies

    def set_number(self, number):
        self._number = number

    def get_number(self):
        return self._number

    @staticmethod
    def _get_dom_node_value(node):
        value = None
        if node.firstChild.nodeType == xml.dom.Node.TEXT_NODE:
            value = node.firstChild.nodeValue

        return value

    @staticmethod
    def _get_dom_child_node_value_by_tag(parent_node, tag):
        for node in parent_node.childNodes:
            if (node.nodeType == node.ELEMENT_NODE and
                    node.tagName == tag):
                return node.firstChild.nodeValue
        return None

    @staticmethod
    def _get_dom_nodes_values_by_tag(dom, tag):
        result = []

        nodes = dom.getElementsByTagName(tag)
        for node in nodes:
            value = MSBuildXmlProject._get_dom_node_value(node)
            if value:
                result.append(value)

        return result

    def get_output_types(self):
        this_project_dom = self._get_project_dom()

        if this_project_dom is None:
            return None

        output_types = set()

        # For *.vcxproj output type stored under tag 'ConfigurationType'
        config_type_values = MSBuildXmlProject._get_dom_nodes_values_by_tag(
            this_project_dom, 'ConfigurationType')
        if config_type_values:
            output_types.update(config_type_values)

        # For *.csproj output type stored under tag 'OutputType'
        output_values = MSBuildXmlProject._get_dom_nodes_values_by_tag(
            this_project_dom, 'OutputType')
        if output_values:
            output_types.update(output_values)

        return output_types if output_types else None

    def _collect_dependencies_attribute_by_info(self, all_projects, new_detected_projects, info):
        this_project_dom = self._get_project_dom()

        if this_project_dom is None:
            return

        dependencies_list = info.item.get_dependencies(this_project_dom, info.dependencies_masks)
        for dependency in dependencies_list:
            dependency_abs_path = self._get_project_abs_path(dependency)
            dependency_abs_path_lower = dependency_abs_path.lower()
            if dependency_abs_path_lower not in all_projects:
                current_project_dependency =\
                    MSBuildXmlProject(dependency_abs_path, self.dependenies_info)
                new_detected_projects.add(current_project_dependency)
            else:
                current_project_dependency = all_projects[dependency_abs_path_lower]

            self._add_project_dependency(current_project_dependency)

    def collect_dependencies(self, all_projects, new_detected_projects):
        if not self.is_project_exists():
            return

        for info in self.dependenies_info:
            self._collect_dependencies_attribute_by_info(all_projects, new_detected_projects, info)


class DirectoryNode:
    def __init__(self, directory_name):
        self.directory_name = directory_name
        self.parent = None
        self.childrens = []
        self.items_in_directory = []

    def __str__(self):
        return self.get_directory_name()

    def add_child(self, child):
        child._set_parent(self)
        self.childrens.append(child)

    def _set_parent(self, parent):
        self.parent = parent

    def add_item_to_directory(self, item):
        self.items_in_directory.append(item)

    def is_root(self):
        return True if not self.parent else False

    def get_directory_name(self):
        return self.directory_name


class DirectoryPathsBranch:
    def __init__(self):
        self.nodes = []

    def _add_node(self, directory_path):
        parent_node = self.nodes[-1]
        new_node = DirectoryNode(directory_path)
        parent_node.add_child(new_node)
        self.nodes.append(new_node)

    def add_node(self, directory_path):
        directory_path_obj = pathlib.PurePath(directory_path)

        if self.nodes:
            last_node_obj = pathlib.PurePath(self.nodes[-1].get_directory_name())

            if last_node_obj == directory_path_obj:
                logging.info("Path [%s] already added to the branch", str(last_node_obj))
                return

            if last_node_obj not in directory_path_obj.parents:
                raise Exception('Incorrect directory path [{0}] for '
                                'the current paths branch=[{1}]'.format(
                                    directory_path, str(last_node_obj)))

            # search for parent position in the parent list
            number_parents_not_in_list = 0
            while directory_path_obj.parents[number_parents_not_in_list] != last_node_obj:
                number_parents_not_in_list += 1

            # add parents of the directory_path to the branch
            while number_parents_not_in_list != 0:
                self._add_node(str(directory_path_obj.parents[number_parents_not_in_list - 1]))
                number_parents_not_in_list -= 1

            # add directory yourself to the branch
            self._add_node(directory_path)

        else:
            self.nodes.append(DirectoryNode(directory_path))

    def get_tip(self):
        return self.nodes[-1] if self.nodes else None

    def get_root(self):
        return self.nodes[0] if self.nodes else None

    def can_grow_to(self, directory_path_grow_to):
        last_node = self.get_tip()
        last_node_dir = pathlib.PurePath(last_node.get_directory_name())

        directory_path_grow_to_obj = pathlib.PurePath(directory_path_grow_to)
        can_grow = True if last_node_dir in directory_path_grow_to_obj.parents else False

        return can_grow

    def truncate_until(self, directory_path):
        directory_path_obj = pathlib.PurePath(directory_path)

        while pathlib.PurePath(self.nodes[-1].get_directory_name()) != directory_path_obj:
            del self.nodes[-1]


def build_directory_tree(projects):
    if not projects:
        return None

    common_directory_path = os.path.commonpath(
        [project.get_project_filepath() for project in projects])

    # when len(projects) == 1 common_directory_path is a project file path, not a directory
    if len(projects) == 1:
        common_directory_path = os.path.dirname(common_directory_path)

    tree_branch = DirectoryPathsBranch()
    tree_branch.add_node(common_directory_path)

    projects_sorted = sorted(list(projects))

    for project in projects_sorted:
        # parent node always is a last item in the list
        tip_node = tree_branch.get_tip()
        tip_node_dir = pathlib.PurePath(tip_node.get_directory_name())
        project_dir = pathlib.PurePath(project.get_project_directory())
        if project_dir == tip_node_dir:
            # project is situated in the current directory
            tip_node.add_item_to_directory(project)
            continue

        if not tree_branch.can_grow_to(project_dir):
            # the project is located in another sub branch
            common_path = os.path.commonpath((project_dir, tip_node_dir))
            tree_branch.truncate_until(common_path)

        # grow branch
        tree_branch.add_node(project.get_project_directory())

        tip_node = tree_branch.get_tip()
        tip_node.add_item_to_directory(project)

    return tree_branch.get_root()


def print_node_items(directory_node):
    if directory_node.items_in_directory:
        print('Node items:\n\t{}'.format(
            '\n\t'.join((str(item) for item in directory_node.items_in_directory))))


def print_node(directory_node, print_childrens=False):
    if print_childrens:
        print('NODE\n{}\n\tCHILDRENS\n\t{}'.format(
            directory_node,
            '\n\t'.join((str(node) for node in directory_node.childrens))))
    else:
        print('NODE\n{}'.format(directory_node))


def print_directory_tree(root_node):
    if not root_node:
        return

    print_node(root_node)
    print_node_items(root_node)

    for child in root_node.childrens:
        print_directory_tree(child)


class DependenciesCollector:
    '''This class is intended to collect dependencies of the MSBuildXml projects'''
    def __init__(self, dependenies_info):
        self.dependenies_info = dependenies_info

    def collect_dependencies(self, project_file_paths_list):
        projects = set(MSBuildXmlProject(path, self.dependenies_info)
                       for path in project_file_paths_list)

        all_projects = dict((project.get_project_filepath().lower(), project)
                            for project in projects)
        processed_projects = set()
        new_detected_projects = set()
        projects_to_process = projects.copy()

        while projects_to_process:
            project = projects_to_process.pop()
            # search for project dependencies
            new_detected_projects.clear()
            project.collect_dependencies(all_projects,
                                         new_detected_projects)
            processed_projects.add(project)

            # populate all_projects with a new found projects
            all_projects.update(
                (it.get_project_filepath().lower(), it) for it in new_detected_projects)

            # save items to find their dependencies later in the next iterations
            projects_to_process.update(it for it in new_detected_projects)

        # enumerate projects
        project_number = 0
        for project in processed_projects:
            project.set_number(project_number)
            project_number = project_number + 1

        existing_projects = set(item for item in processed_projects
                                if item.is_project_exists())
        unknown_projects = processed_projects - existing_projects

        return existing_projects, unknown_projects


_global_unknown_node_style = dict(
    shape='box',
    style='dashed',
    color='red',
    )


_global_unknown_edge_style = dict(
    color='red',
    )


class ProjectDependencyPrinter:
    def __init__(self, projects_settings):
        self.projects_settings = projects_settings

    @staticmethod
    def set_default_graph_settings(dot_graph):
        default_node_style = dict(
            rankdir='LR',
            style='dotted, bold',
            color='grey',
            fontcolor='darkgreen',
            fontsize='16',
            labelloc='t'
            )
        # WARNING!
        # using of "newrank='false'" parameter with any value (true or false)
        # give us sometimes the render-error:
        #   "Error: trouble in init_rank"
        # It is graphviz bug. Possibly this bug will be fixed in the next version
        # of the graphviz (after 2.38).

        dot_graph.attr(**default_node_style)

    @staticmethod
    def set_default_graph_nodes_settings(dot_graph):
        default_node_style = dict(
            shape='box',
            style='filled, rounded',
            color='brown',
            fillcolor='beige',
            penwidth='2'
            )

        dot_graph.attr('node', **default_node_style)

    @staticmethod
    def get_project_output_type_color(project):
        project_colors_dict = dict({
            'DEFAULT': 'brown',
            'MIXED': 'orangered',
            # *.vcxproj
            'dynamiclibrary': 'blue',
            'driver': 'magenta',
            'staticlibrary': 'deepskyblue',
            'application': 'limegreen',
            # *.csproj
            'library' : 'cornflowerblue',
            'module' : 'darkviolet',
            'exe' : 'green',
            'winexe' : 'greenyellow',
        })

        # more colors here:
        # https://www.graphviz.org/doc/info/colors.html

        color = project_colors_dict['DEFAULT']

        output_types = project.get_output_types()
        if output_types is None:
            return color

        output_types = [type.lower() for type in output_types]

        if len(output_types) > 1:
            color = project_colors_dict['MIXED']
        else:
            color = project_colors_dict.get(
                output_types.pop(), project_colors_dict['DEFAULT'])

        return color

    @staticmethod
    def set_default_graph_edges_settings(dot_graph):
        default_edge_style = dict(
            color='brown',
            )

        dot_graph.attr('edge', **default_edge_style)

    @staticmethod
    def make_subgraph_name_by_path(project_path, hide_paths):
        prefix = 'cluster_'

        if hide_paths:
            prefix = ''

        name = project_path
        for character in (os.path.sep, ':', '.'):
            name = name.replace(character, '_')

        return prefix + name

    @staticmethod
    def print_directories_tree(directory_node, parent_dot_object, common_path, hide_paths):
        if not directory_node:
            return

        if not parent_dot_object:
            raise Exception('Parent dot object is not specified')

        current_path = directory_node.get_directory_name()

        if not common_path:
            # directory_node should be the root
            common_path = current_path

        subgraph_name = ProjectDependencyPrinter.make_subgraph_name_by_path(
            current_path, hide_paths)
        with parent_dot_object.subgraph(name=subgraph_name) as new_subgraph:
            # print full path only for root subgraph
            # add last separator for all
            if common_path == current_path:
                label_text = os.path.join(current_path, '')
            else:
                label_text = os.path.join(current_path, '')[len(common_path) + 1:]

            new_subgraph.attr(label=label_text.replace('\\', '/'))

            for project in directory_node.items_in_directory:
                node_color = ProjectDependencyPrinter.get_project_output_type_color(project)
                new_subgraph.node('node' + str(project.get_number()),
                                  project.get_project_filename(),
                                  color=node_color,
                                  tooltip=project.get_project_filepath())

            for child in directory_node.childrens:
                ProjectDependencyPrinter.print_directories_tree(child,
                                                                new_subgraph,
                                                                common_path,
                                                                hide_paths)

    def print_projects(self, projects, parent_graph, **kwarg):
        for project in projects:
            parent_graph.node('node' + str(project.get_number()),
                              project.get_project_filepath().replace('\\', '/'),
                              kwarg)

    def _should_ignore_project_deps(self, project):
        should_ignore = False

        if self.projects_settings.ignore_deps:
            for ignore in self.projects_settings.ignore_deps:
                if project.get_project_filepath().lower().endswith(ignore.lower()):
                    should_ignore = True
                    break

        return should_ignore

    def create_projects_diagram(self, gv_settings):

        logging.info('Collecting projects dependencies...')
        dependencies_collector = DependenciesCollector(self.projects_settings.dependenies_info)
        existing_projects, unknown_projects = \
            dependencies_collector.collect_dependencies(
                self.projects_settings.get_all_projects())

        logging.info('Printing projects...')

        digraph_object = graphviz.Digraph(name=gv_settings.graph_name,
                                          comment=gv_settings.comment,
                                          filename=gv_settings.filename,
                                          directory=gv_settings.directory,
                                          format=gv_settings.output_format,
                                          engine=gv_settings.engine)

        ProjectDependencyPrinter.set_default_graph_settings(digraph_object)
        ProjectDependencyPrinter.set_default_graph_nodes_settings(digraph_object)
        ProjectDependencyPrinter.set_default_graph_edges_settings(digraph_object)
        digraph_object.attr(label=gv_settings.diagram_label)

        directories_tree = build_directory_tree(existing_projects)
        #print_node(directories_tree)
        #print_node(directories_tree.childrens[0], True)
        #print_node(directories_tree.childrens[1])
        #print_node(directories_tree.childrens[2])
        #print_directory_tree(directories_tree)

        # print edges
        for project in existing_projects:
            if self._should_ignore_project_deps(project):
                # do not print dependencies for the projects to be ignored
                continue

            project_name = project.get_project_filename()
            for dependency_project in project.get_project_dependencies():
                if self._should_ignore_project_deps(dependency_project):
                    # do not print projects to be ignored
                    continue

                dependency_project_name = dependency_project.get_project_filename()

                if self.projects_settings.ignore_std and \
                    is_standard_project(dependency_project_name):
                    continue

                edge_tooltip = project_name + " -> "  + dependency_project_name
                edge_color = ProjectDependencyPrinter.get_project_output_type_color(
                    dependency_project)
                if not dependency_project.is_project_exists():
                    edge_color = _global_unknown_edge_style['color']

                digraph_object.edge('node' + str(project.get_number()),
                                    'node' + str(dependency_project.get_number()),
                                    tooltip=edge_tooltip,
                                    color=edge_color)

        # print nodes for existing projects
        self.print_directories_tree(directories_tree, digraph_object, None, gv_settings.hide_paths)

        # print nodes for unknown projects
        self.print_projects(unknown_projects, digraph_object,
                            **_global_unknown_node_style)

        if gv_settings.need_render:
            digraph_object.render()
        else:
            digraph_object.save()
        #digraph_object.view()
        logging.info('Projects printed')


class GraphVizSettings:
    def __init__(self, graph_name, comment, filename, directory,
                 output_format, engine, diagram_label, need_render,
                 hide_paths):
        self.graph_name = graph_name
        self.comment = comment
        self.filename = filename
        self.directory = directory
        self.output_format = output_format
        self.engine = engine
        self.diagram_label = diagram_label
        self.need_render = need_render
        self.hide_paths = hide_paths


class ProjectsSettings:
    def __init__(self, projects, solutions, dependenies_info, config, ignore_std, ignore_deps):
        self.projects = projects
        self.solutions = solutions
        self.dependenies_info = dependenies_info
        self.config = config
        self.ignore_std = ignore_std
        self.ignore_deps = ignore_deps

    @staticmethod
    def get_projects_contents(sln_content):
        pattern = re.compile(r'\bProject\(.+?\bEndProject\b', re.DOTALL)

        return pattern.findall(sln_content)

    @staticmethod
    def parse_solution(sln_filepath):
        projects_paths = []
        sln_filepath_abs = os.path.abspath(sln_filepath)

        for guess_encoding in ('utf-8', 'utf-16', 'cp1252', None):
            try:
                logging.debug('Try to read the solution [%s] using encoding: [%s]',
                              sln_filepath_abs, guess_encoding)
                with open(sln_filepath_abs, 'rt', encoding=guess_encoding) as sln_file:
                    sln_content = sln_file.read()
            except UnicodeError:
                logging.debug('Failed to read the solution using encoding: %s', guess_encoding)
                continue
            else:
                break

        projects_contents = ProjectsSettings.get_projects_contents(sln_content)

        for content in projects_contents:
            project_path = content.split(',')[1].strip(' "')

            # TODO: should we use 'proj' here?
            if project_path.endswith('proj'):
                if not os.path.isabs(project_path):
                    project_path = os.path.normpath(
                        os.path.join(os.path.dirname(sln_filepath_abs), project_path))
                    projects_paths.append(project_path)

        return projects_paths

    def get_all_projects(self):
        all_projects = []
        if self.projects:
            all_projects += [os.path.abspath(project) for project in self.projects]
        if self.solutions:
            for sln in self.solutions:
                sln_projects = ProjectsSettings.parse_solution(sln)
                all_projects += sln_projects

        return all_projects


def parse_arguments(args_list):
    arg_parser = argparse.ArgumentParser(
        description='Print Visual Studio projects dependencies.')

    projects_group = arg_parser.add_argument_group(
        'Projects', 'Arguments for printing a project dependencies')
    graphviz_group = arg_parser.add_argument_group(
        'Graphviz', 'Arguments for the graphviz')

    projects_group.add_argument('--proj',
                                metavar='ProjectFilePath',
                                action='append')
    projects_group.add_argument('--sln',
                                metavar='SolutionFilePath',
                                action='append')
    projects_group.add_argument('--dep-item',
                                nargs='+',
                                choices=[t.value for t in MSBuildItems],
                                metavar=('Item1', 'Item2'),
                                help='MSBuild xml item(s). '
                                     'Possible items: %(choices)s')
    projects_group.add_argument('--dep-masks',
                                nargs='*',
                                metavar='.file_extension',
                                help='Dependency files extensions masks for the accounting. '
                                'For example: ".targets" ".props" ".settings", etc')

    projects_group.add_argument('--ignore-deps',
                                metavar='ProjectFileName',
                                action='append',
                                help='Do not print dependenices for/from the project on the image')

    config_help = r'ini-config file path. '\
                  r'This file is used to resolve variables of the projects. '\
                  r'Variables should be defined at [DEFAULT] section. '\
                  r'For example: $(SolutionDir)=C:\SolutionDir\ '
    projects_group.add_argument('--config',
                                help=config_help)
    std_proj_help = r'Ignore standard projects like'\
                    r' "$(VCTargetsPath)\Microsoft.Cpp.Default.props",'\
                    r' "$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"'\
                    r' and "$(VCTargetsPath)\Microsoft.Cpp.targets"'
    projects_group.add_argument('--ignore-std-proj',
                                dest='ignore_std',
                                action='store_true',
                                help=std_proj_help)

    graphviz_group.add_argument('--name', default='Dependencies',
                                help='Graph name used in the source code.')
    graphviz_group.add_argument('--comment', default='Dependencies for projects',
                                help='Comment added to the first line of the source.')
    graphviz_group.add_argument('--label', default='Dependencies',
                                help='Label of the graph in the image')
    graphviz_group.add_argument('--outfilename', default='project_dependencies.gv',
                                help="Filename for saving the source")
    graphviz_group.add_argument('--outdir', default='.out',
                                help="(Sub)directory for source saving and rendering")
    graphviz_group.add_argument('--outformat', default='svg',
                                help="Rendering output format ('pdf', 'png', ...)")
    graphviz_group.add_argument('--engine', default='dot',
                                help="Layout command used ('dot', 'neato', ...)")
    graphviz_group.add_argument('--with-render', dest='need_render', action='store_true',
                                help="Render the source *.gv file with the engine to an image")
    graphviz_group.add_argument('--without-paths', dest='hide_paths', action='store_true',
                                help='Do not add projects path to the image')

    args = arg_parser.parse_args(args=args_list)

    if not args.proj and not args.sln:
        print('You should specify at least --proj or --sln parameter')
        arg_parser.print_help()
        sys.exit(1)

    dependency_info_list = []
    for item in args.dep_item:
        dependency_info_list.append(MSBuildItemDependencyInfo(item, args.dep_masks))

    proj_settings = ProjectsSettings(args.proj,
                                     args.sln,
                                     dependency_info_list,
                                     args.config,
                                     args.ignore_std,
                                     args.ignore_deps)

    gv_settings = GraphVizSettings(args.name, args.comment, args.outfilename,
                                   args.outdir, args.outformat, args.engine,
                                   args.label, args.need_render, args.hide_paths)

    return proj_settings, gv_settings


def parse_config(config_filepath):
    # prevent ignoring case sensitivity
    _global_projects_config.optionxform = lambda option: option
    _global_projects_config.read(config_filepath)


def print_dependencies(args_list=None):
    proj_settings, gv_settings = parse_arguments(args_list)

    if proj_settings.config:
        parse_config(proj_settings.config)

    pdp = ProjectDependencyPrinter(proj_settings)
    pdp.create_projects_diagram(gv_settings)


def main():
    logging_format = '%(asctime)s %(levelname)s: %(message)s'
    logging.basicConfig(format=logging_format, level=logging.DEBUG)

    start_time = time.perf_counter()
    print_dependencies()
    end_time = time.perf_counter()
    logging.info('Total time spent: %0.7f secs', end_time - start_time)


if __name__ == '__main__':
    main()
