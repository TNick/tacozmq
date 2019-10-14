# -*- coding: utf-8 -*-
"""
Small functions that are needed in several parts.
"""
import os


def norm_path(inp):
    """ Converts input path into an absolute, normalized path. """
    return os.path.normpath(os.path.abspath(inp))


def norm_join(*args):
    """ Like os.path.join but also normalizes the path. """
    return norm_path(os.path.join(*args))


class ShutDownException(Exception):
    pass
