import sys
import os
import pdv
import logging

def traverse_for_projects(root_dir):
    num = 0
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith('proj'):
                num += 1
                project_file = os.path.join(root, file)
                logging.debug('Processing: %s', project_file)
                params_list = ['--proj', project_file,
                               '--dep-item', 'ProjectReference', 'ProjectReference2',
                               '--outdir', '.out_projects',
                               '--outfilename', file + '_ProjectReference_' + str(num) + '.dot',
                                '--with-render'
                              ]
                pdv.print_dependencies(params_list)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    root_dir = sys.argv[1]
    traverse_for_projects(root_dir)
