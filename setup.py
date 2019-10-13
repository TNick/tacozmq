#!/bin/env python
# -*- coding: utf-8 -*-

try:
    from setuptools import setup
    from setuptools import Command
except ImportError:
    from distutils.core import setup
    from distutils.cmd import Command
from setuptools.command.develop import develop
from setuptools import find_packages
import sys
sys.setrecursionlimit(5000)
import glob

cmdclass = {}


config = {
    'name': 'TacoZMQ',
    'description': 'a friend to friend darknet',
    'author': 'Scott Powers',
    'url': 'https://github.com/TheTacoScott/tacozmq/wiki',
    'download_url': 'https://github.com/TNick/tacozmq',
    'author_email': '',
    'version': '0.3.0',
    'install_requires': [
        'argparse',
        'appdirs',
        'pyzmq',
        'bottle',
        'cherrypy < 9.0.0',
        'u-msgpack-python'
    ],
    'packages': find_packages(),
    'package_data': {
        'schema': [],
    },
    'scripts': ['tacozmq.py'],
    'entry_points': {},
    'extras_require': {
        'dev': [
            'pytest',
            'pytest-pep8',
            'pytest-cov',
        ]
     },
    'cmdclass': cmdclass
}

setup(**config)
