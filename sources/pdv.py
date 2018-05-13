import os
import sys
import pathlib
import xml.dom
import xml.dom.minidom as minidom
from enum import Enum
import argparse
import configparser
import re

import graphviz

# projects config is intended to resolve variables in the projects paths
_global_projects_config = configparser.ConfigParser()


class MSBuildXmlProjectType(Enum):
    XPROJ = 'proj'    # vcxproj, vbproj, csproj, pyproj, etc.
    PROPS = '.props'
    TARGETS = '.targets'

    def get_project_class(self):
        return {MSBuildXmlProjectType.XPROJ: XProject,
                MSBuildXmlProjectType.PROPS: PropsProject,
                MSBuildXmlProjectType.TARGETS: TargetsProject}[self]

    @staticmethod
    def get_project_by_path(path):
        abs_path = os.path.abspath(path)
        abs_path_lower = abs_path.lower()

        if abs_path_lower.endswith(MSBuildXmlProjectType.XPROJ.value):
            return XProject(abs_path)
        elif abs_path_lower.endswith(MSBuildXmlProjectType.PROPS.value):
            return PropsProject(abs_path)
        elif abs_path_lower.endswith(MSBuildXmlProjectType.TARGETS.value):
            return TargetsProject(abs_path)
        else:
            raise Exception("Unexpected file type [{}]".format(path))


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
    '''Instance of this class is "*proj" or "*.props" or "*.targets" file'''
    def __init__(self, project_file_path):
        self.file_path = project_file_path
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
            print('Project [{}] already present as dependency for [{}]'.format(
                project.get_project_filepath(), self.get_project_filepath()))
            return

        self.proj_dependencies.add(project)

    def _get_project_dom(self):
        if self._dom is None:
            if not self.is_project_exists():
                print("Failed to parse xml. File [{}] not found.".format(self.file_path))
                return None
            self._dom = minidom.parse(self.file_path)
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

        # some variables may not have been resolved
        if os.path.isfile(resolved_path):
            # assume path was resolved as absolute
            # TODO: if this assumption is wrong then fix it
            return os.path.normpath(resolved_path)

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

    def get_configuration_types(self):
        return None

    def _collect_props_or_targets_dependencies(self, dep_type, all_projects,
                                               new_detected_projects):
        if (dep_type is not MSBuildXmlProjectType.TARGETS and
                dep_type is not MSBuildXmlProjectType.PROPS):
            raise Exception('Incorrect dependency type specified')

        this_project_dom = self._get_project_dom()

        if this_project_dom is None:
            return

        imports = this_project_dom.getElementsByTagName('Import')
        for element in imports:
            if element.hasAttribute('Project'):
                project_attr = element.getAttribute('Project')
                project_attr_lower = project_attr.lower()

                # TODO: projects can be imported with a condition
                # so we should take into account this case
                if project_attr_lower.endswith(dep_type.value):
                    project_abs_path = self._get_project_abs_path(project_attr)
                    project_abs_path_lower = project_abs_path.lower()
                    if project_abs_path_lower not in all_projects:
                        current_project_dependency = \
                            dep_type.get_project_class()(project_abs_path)
                        new_detected_projects.add(current_project_dependency)
                    else:
                        current_project_dependency = all_projects[project_abs_path_lower]

                    self._add_project_dependency(current_project_dependency)

    def collect_project_dependencies(self, all_projects, new_detected_projects,
                                     dependencies_type):
        if not self.is_project_exists():
            return

        if dependencies_type == MSBuildXmlProjectType.XPROJ:
            self.collect_proj_ref_dependencies(all_projects, new_detected_projects)
        elif dependencies_type == MSBuildXmlProjectType.PROPS:
            self.collect_props_dependencies(all_projects, new_detected_projects)
        elif dependencies_type == MSBuildXmlProjectType.TARGETS:
            self.collect_targets_dependencies(all_projects, new_detected_projects)
        else:
            raise Exception("Incorrect dependencies type given=[{0}]".format(
                dependencies_type))

    def collect_proj_ref_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_proj_ref_dependencies() for the "
                        "MSBuildXmlProject class is not implemented")

    def collect_props_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_props_dependencies() for the "
                        "MSBuildXmlProject class is not implemented")

    def collect_targets_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_targets_dependencies() for the "
                        "MSBuildXmlProject class is not implemented")


class XProject(MSBuildXmlProject):
    '''Instance of this class is representation of
       ".vcxproj", ".vbproj", ".csproj", ".pyproj", etc. file'''

    def __init__(self, project_file_path):
        super().__init__(project_file_path)

    @staticmethod
    def _get_proj_ref_node_tag_value(prject_node, tag):
        for node in prject_node.childNodes:
            if (node.nodeType == node.ELEMENT_NODE and
                    node.tagName == tag):
                return node.firstChild.nodeValue
        return None

    def collect_proj_ref_dependencies(self, all_projects, new_detected_projects):
        this_project_dom = self._get_project_dom()

        if this_project_dom is None:
            return

        projects_ref_nodes = this_project_dom.getElementsByTagName('ProjectReference')

        for project_node in projects_ref_nodes:
            if project_node.hasAttribute('Include'):
                project_ref_path = project_node.getAttribute('Include')

                if project_ref_path.lower().endswith(MSBuildXmlProjectType.XPROJ.value):
                    project_abs_path = self._get_project_abs_path(project_ref_path)
                    project_abs_path_lower = project_abs_path.lower()
                    if project_abs_path_lower not in all_projects:
                        current_project_dependency = XProject(project_abs_path)
                        new_detected_projects.add(current_project_dependency)

                        #project_ref_guid = XProject._get_proj_ref_node_tag_value(
                        #    project_node, 'Project')
                        #project_ref_name = XProject._get_proj_ref_node_tag_value(
                        #    project_node, 'Name')
                        #print('GUID = [{}]\nNAME = [{}]'.format(
                        #    project_ref_guid, project_ref_name))
                    else:
                        current_project_dependency = all_projects[project_abs_path_lower]

                    self._add_project_dependency(current_project_dependency)

    def collect_props_dependencies(self, all_projects, new_detected_projects):
        super()._collect_props_or_targets_dependencies(
            MSBuildXmlProjectType.PROPS, all_projects, new_detected_projects)

    def collect_targets_dependencies(self, all_projects, new_detected_projects):
        super()._collect_props_or_targets_dependencies(
            MSBuildXmlProjectType.TARGETS, all_projects, new_detected_projects)

    def get_configuration_types(self):
        this_project_dom = self._get_project_dom()

        if this_project_dom is None:
            return None

        config_type_nodes = this_project_dom.getElementsByTagName('ConfigurationType')
        config_types = set()
        for type_node in config_type_nodes:
            if type_node.firstChild.nodeType == xml.dom.Node.TEXT_NODE:
                config_types.add(type_node.firstChild.nodeValue)

        return config_types if config_types else None


class PropsProject(MSBuildXmlProject):

    def __init__(self, projectFilePath):
        super().__init__(projectFilePath)

    def collect_proj_ref_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_proj_ref_dependencies() for the "
                        "PropsProject class is not implemented")

    def collect_targets_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_targets_dependencies() for the "
                        "PropsProject class is not implemented")

    def collect_props_dependencies(self, all_projects, new_detected_projects):
        super()._collect_props_or_targets_dependencies(
            MSBuildXmlProjectType.PROPS, all_projects, new_detected_projects)


class TargetsProject(MSBuildXmlProject):

    def __init__(self, projectFilePath):
        super().__init__(projectFilePath)

    def collect_proj_ref_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_proj_ref_dependencies() for the "
                        "TargetsProject class is not implemented")

    def collect_props_dependencies(self, all_projects, new_detected_projects):
        raise Exception("collect_props_dependencies() for the "
                        "TargetsProject class is not implemented")

    def collect_targets_dependencies(self, all_projects, new_detected_projects):
        super()._collect_props_or_targets_dependencies(
            MSBuildXmlProjectType.TARGETS, all_projects, new_detected_projects)


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
                print("Path [{}] already added to the branch".format(last_node_obj))
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
    def __init__(self, ms_build_project_type):
        self.type = ms_build_project_type

    def collect_dependencies(self, project_file_paths_list):
        projects = set()
        for path in project_file_paths_list:
            next_project = MSBuildXmlProjectType.get_project_by_path(path)
            projects.add(next_project)

        all_projects = dict((project.get_project_filepath().lower(), project)
                            for project in projects)
        processed_projects = set()
        new_detected_projects = set()
        projects_to_process = projects.copy()

        while projects_to_process:
            project = projects_to_process.pop()
            # search for project dependencies
            new_detected_projects.clear()
            project.collect_project_dependencies(all_projects,
                                                 new_detected_projects,
                                                 self.type)
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
    def get_project_config_type_color(project):
        project_colors_dict = dict({
            'DEFAULT': 'brown',
            'MIXED': 'orangered',
            'DynamicLibrary': 'blue',
            'Driver': 'magenta',
            'StaticLibrary': 'deepskyblue',
            'Application': 'limegreen',
        })

        config_types = project.get_configuration_types()

        color = project_colors_dict['DEFAULT']

        if config_types is None:
            return color

        if len(config_types) > 1:
            color = project_colors_dict['MIXED']
        else:
            color = project_colors_dict.get(
                config_types.pop(), project_colors_dict['DEFAULT'])

        return color

    @staticmethod
    def set_default_graph_edges_settings(dot_graph):
        default_edge_style = dict(
            color='brown',
            )

        dot_graph.attr('edge', **default_edge_style)

    @staticmethod
    def make_cluster_name_by_path(project_path):
        return 'cluster_' + project_path.replace(os.path.sep, '_').replace(':', '_')

    @staticmethod
    def print_directories_tree(directory_node, parent_dot_object, common_path):
        if not directory_node:
            return

        if not parent_dot_object:
            raise Exception('Parent dot object is not specified')

        current_path = directory_node.get_directory_name()

        if not common_path:
            # directory_node should be the root
            common_path = current_path

        subgraph_name = ProjectDependencyPrinter.make_cluster_name_by_path(
            current_path)
        with parent_dot_object.subgraph(name=subgraph_name) as new_subgraph:
            # print full path only for root subgraph
            # add last separator for all
            if common_path == current_path:
                label_text = os.path.join(current_path, '')
            else:
                label_text = os.path.join(current_path, '')[len(common_path) + 1:]

            new_subgraph.attr(label=label_text.replace('\\', '/'))

            for project in directory_node.items_in_directory:
                node_color = ProjectDependencyPrinter.get_project_config_type_color(project)
                new_subgraph.node('node' + str(project.get_number()),
                                  project.get_project_filename(),
                                  color=node_color)

            for child in directory_node.childrens:
                ProjectDependencyPrinter.print_directories_tree(child,
                                                                new_subgraph,
                                                                common_path)

    def print_projects(self, projects, parent_graph, **kwarg):
        for project in projects:
            parent_graph.node('node' + str(project.get_number()),
                              project.get_project_filepath().replace('\\', '/'),
                              kwarg)

    def create_projects_diagram(self, gv_settings):

        print('Collecting projects dependencies...')
        dependencies_collector = DependenciesCollector(self.projects_settings.dependency_type)
        existing_projects, unknown_projects = \
            dependencies_collector.collect_dependencies(
                self.projects_settings.get_all_projects())

        print('Printing projects...')

        digraph_object = graphviz.Digraph(name=gv_settings.graph_name,
                                          comment=gv_settings.comment,
                                          filename=gv_settings.filename,
                                          directory=gv_settings.directory,
                                          format=gv_settings.output_format,
                                          engine=gv_settings.engine)

        ProjectDependencyPrinter.set_default_graph_settings(digraph_object)
        ProjectDependencyPrinter.set_default_graph_nodes_settings(digraph_object)
        ProjectDependencyPrinter.set_default_graph_edges_settings(digraph_object)
        digraph_object.attr(label=gv_settings.diagram_name)

        directories_tree = build_directory_tree(existing_projects)
        #print_node(directories_tree)
        #print_node(directories_tree.childrens[0], True)
        #print_node(directories_tree.childrens[1])
        #print_node(directories_tree.childrens[2])
        #print_directory_tree(directories_tree)

        # print edges
        for project in existing_projects:
            project_name = project.get_project_filename()
            for dependency_project in project.get_project_dependencies():
                dependency_project_name = dependency_project.get_project_filename()
                if self.projects_settings.ignore_std and \
                    is_standard_project(dependency_project_name):
                    continue

                edge_comment = project_name + " -> "  + dependency_project_name
                edge_color = ProjectDependencyPrinter.get_project_config_type_color(
                    dependency_project)
                if not dependency_project.is_project_exists():
                    edge_color = _global_unknown_edge_style['color']

                digraph_object.edge('node' + str(project.get_number()),
                                    'node' + str(dependency_project.get_number()),
                                    comment=edge_comment,
                                    color=edge_color)

        # print nodes for existing projects
        self.print_directories_tree(directories_tree, digraph_object, None)

        # print nodes for unknown projects
        self.print_projects(unknown_projects, digraph_object,
                            **_global_unknown_node_style)

        if gv_settings.need_render:
            digraph_object.render()
        else:
            digraph_object.save()
        #digraph_object.view()
        print('Projects printed')


class GraphVizSettings:
    def __init__(self, graph_name, comment, filename, directory,
                 output_format, engine, diagram_name, need_render):
        self.graph_name = graph_name
        self.comment = comment
        self.filename = filename
        self.directory = directory
        self.output_format = output_format
        self.engine = engine
        self.diagram_name = diagram_name
        self.need_render = need_render


def is_utf_encoding(data, utf8_utf16_encoding):
    try:
        data.decode(utf8_utf16_encoding)
    except UnicodeDecodeError:
        return False
    else:
        return True


class ProjectsSettings:
    def __init__(self, projects, solutions, dtype, config, ignore_std):
        self.projects = projects
        self.solutions = solutions
        self.dependency_type = dtype
        self.config = config
        self.ignore_std = ignore_std

    @staticmethod
    def get_project_content_gen(sln_content):
        begin = 'Project'
        end = 'EndProject'

        section_begin = 0
        section_end = 0
        new_search_pos = 0

        while True:
            try:
                section_begin = sln_content.index(begin, new_search_pos) + len(begin)
                section_end = sln_content.index(end, section_begin)

                project_content = sln_content[section_begin:section_end]
                yield project_content

                new_search_pos = section_end + len(end)
            except ValueError:
                break

    @staticmethod
    def determine_sln_encoding(sln_filepath):
        '''usually *.sln files have encoding "utf-8" or "utf-16"'''
        encoding = None
        with open(sln_filepath, 'rb') as sln_file:
            # try read only BOM
            data = sln_file.read(4)
            if is_utf_encoding(data, 'utf-8'):
                encoding = 'utf-8'
            elif is_utf_encoding(data, 'utf-16'):
                encoding = 'utf-16'
            else:
                pass

        return encoding

    @staticmethod
    def parse_solution(sln_filepath):
        projects_paths = []
        sln_filepath_abs = os.path.abspath(sln_filepath)
        guess_encoding = ProjectsSettings.determine_sln_encoding(sln_filepath_abs)
        with open(sln_filepath_abs, 'rt', encoding=guess_encoding) as sln_file:
            sln_content = sln_file.read()

        projects_contents = list(ProjectsSettings.get_project_content_gen(sln_content))

        for content in projects_contents:
            project_path = content.split(',')[1].strip(' "')

            if project_path.endswith(MSBuildXmlProjectType.XPROJ.value):
                if not os.path.isabs(project_path):
                    project_path = os.path.join(os.path.dirname(sln_filepath_abs), project_path)
                    projects_paths.append(project_path)

        return projects_paths

    def get_all_projects(self):
        all_projects = []
        if self.projects:
            all_projects += self.projects
        if self.solutions:
            for sln in self.solutions:
                sln_projects = ProjectsSettings.parse_solution(sln)
                all_projects += sln_projects

        return all_projects


def parse_arguments():
    arg_parser = argparse.ArgumentParser(
        description='Print Visual Studio projects dependencies.')

    graphviz_group = arg_parser.add_argument_group(
        'Graphviz', 'Arguments for the graphviz')
    projects_group = arg_parser.add_argument_group(
        'Projects', 'Arguments for a printing project dependencies')

    projects_group.add_argument('--dtype',
                                choices=[t.name for t in MSBuildXmlProjectType],
                                required=True)
    projects_group.add_argument('--proj', action='append')
    projects_group.add_argument('--sln', action='append')
    projects_group.add_argument('--config',
                                help='ini config filepath to resolve variables of a projects')
    projects_group.add_argument(
        '--ignore-std-proj', dest='ignore_std', action='store_true',
        help=r'Ignore standard VS projects like "$(VCTargetsPath)\Microsoft.Cpp.Default.props",'
             r' "$(UserRootDir)\Microsoft.Cpp.$(Platform).user.props"'
             r' and "$(VCTargetsPath)\Microsoft.Cpp.targets"')

    graphviz_group.add_argument('--gname', default='Dependencies')
    graphviz_group.add_argument('--gcomment', default='Dependencies for projects')
    graphviz_group.add_argument('--outfilename', default='project_dependencies.gv')
    graphviz_group.add_argument('--outdir', default='.out')
    graphviz_group.add_argument('--outformat', default='svg')
    graphviz_group.add_argument('--engine', default='dot')
    graphviz_group.add_argument('--gdiagname', default='')
    graphviz_group.add_argument('--with-render', dest='need_render', action='store_true')

    args = arg_parser.parse_args()

    if not args.proj and not args.sln:
        print('You should specify at least --proj or --sln parameter')
        arg_parser.print_help()
        sys.exit(1)

    proj_settings = ProjectsSettings(args.proj,
                                     args.sln,
                                     MSBuildXmlProjectType[args.dtype],
                                     args.config,
                                     args.ignore_std)

    if not args.gdiagname:
        args.gdiagname = 'Projects dependencies type [{}]'.format(
            MSBuildXmlProjectType[args.dtype].value)

    gv_settings = GraphVizSettings(args.gname, args.gcomment, args.outfilename,
                                   args.outdir, args.outformat, args.engine,
                                   args.gdiagname, args.need_render)

    return proj_settings, gv_settings


def parse_config(config_filepath):
    # prevent ignoring case sensitivity
    _global_projects_config.optionxform = lambda option: option
    _global_projects_config.read(config_filepath)


def main():
    proj_settings, gv_settings = parse_arguments()

    if proj_settings.config:
        parse_config(proj_settings.config)

    pdp = ProjectDependencyPrinter(proj_settings)
    pdp.create_projects_diagram(gv_settings)


if __name__ == '__main__':
    main()
