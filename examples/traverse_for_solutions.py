import sys
import os
import logging
import pdv


def traverse_for_solutions(root_dir):
    num = 0
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith('.sln'):
                num += 1
                params_list = ['--sln', os.path.join(root, file),
                               '--dep-item', 'ProjectReference', 'ProjectReference2',
                               '--outdir', '.out_solutions',
                               '--outfilename', file + '_ProjectReference_' + str(num) + '.dot',
                                '--with-render'
                              ]
                pdv.print_dependencies(params_list)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    root_dir = sys.argv[1]
    traverse_for_solutions(root_dir)
