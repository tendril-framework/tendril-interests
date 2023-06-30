#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function

import os
from setuptools import setup, find_packages


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    orig_content = open(os.path.join(os.path.dirname(__file__), fname)).readlines()
    content = ""
    in_raw_directive = 0
    for line in orig_content:
        if in_raw_directive:
            if not line.strip():
                in_raw_directive = in_raw_directive - 1
            continue
        elif line.strip() == '.. raw:: latex':
            in_raw_directive = 2
            continue
        content += line
    return content


core_dependencies = [
    'tendril-utils-db>=0.4.3',
    'tendril-auth',
    'networkx',
    'polars',
    'makefun',
    'asgiref',
]

install_requires = core_dependencies + ['wheel']

setup_requires = ['setuptools_scm']

doc_requires = setup_requires + ['sphinx', 'sphinx-argparse', 'alabaster']

test_requires = doc_requires + ['pytest', 'pytest-flake8', 'pytest-cov', 'coveralls[yaml]']

build_requires = test_requires  # + ['doit', 'pyinstaller']

publish_requires = build_requires + ['twine', 'pygithub']

setup(
    name='tendril-interests',
    use_scm_version={"root": ".", "relative_to": __file__},
    author="Chintalagiri Shashank",
    author_email="shashank@chintal.in",
    description="Core Tendril Infrastructure for User Mapped Entitites",
    long_description='\n'.join([read('README.rst'), read('CHANGELOG.rst')]),
    long_description_content_type='text/x-rst',
    keywords='tendril',
    url='https://github.com/tendril-framework/tendril-interests',
    project_urls={
        'Documentation': 'https://tendril-interests.readthedocs.io/en/latest',
        'Bug Tracker': 'https://github.com/tendril-framework/tendril-interests/issues',
        'Source Repository': 'https://github.com/tendril-framework/tendril-interests',
    },
    packages=find_packages('src'),
    package_dir={'': 'src'},
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*',
    install_requires=install_requires,
    setup_requires=setup_requires,
    extras_require={
        'docs': doc_requires,
        'tests': test_requires,
        'build': build_requires,
        'publish': publish_requires,
        'dev': build_requires,
    },
    platforms='any',
    entry_points={
    },
    include_package_data=True
)
