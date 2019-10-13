#!/usr/bin/env python

"""
TacoDARKNET: darknet written in python and zeromq

Author: Scott Powers
"""

import os
import sys
import argparse
import zmq
import logging
import signal
from appdirs import user_data_dir, user_log_dir, user_config_dir
import random
from datetime import datetime

import taco.constants

if zmq.zmq_version_info() < (4, 0):
    raise RuntimeError("Security is not supported in libzmq version < 4.0. "
                       "libzmq version {0}".format(zmq.zmq_version()))
if sys.version_info < (2, 7):
    raise RuntimeError("must use python 2.7 or greater")


def get_config_file(args=None):
    """ Get the path to config file. """
    from taco.constants import APP_AUTHOR, APP_NAME
    if args is not None:
        if len(args.config) > 0 and args.config != '-':
            return args.config
    ucd = user_config_dir(APP_NAME, APP_AUTHOR[0])
    if not os.path.isdir(ucd):
        os.makedirs(ucd)
    return os.path.join(ucd, '%s.cfg' % APP_NAME)


def make_argument_parser():
    """
    Creates an ArgumentParser to read the options for this script from
    sys.argv.
    """
    from taco.constants import APP_AUTHOR, APP_NAME

    parser = argparse.ArgumentParser(
        description='TacoZMQ: a darknet written in python and zeromq')
    parser.add_argument(
        '--config', default=get_config_file(),
        metavar='file', dest='config_file',
        help='specify the location of the config file')
    parser.add_argument(
        "--verbose", default=False,
        action="store_true",
        help="increase output verbosity; equivalent to --log-level=10")
    parser.add_argument(
        "--log-level", default=logging.INFO, type=int,
        metavar="level", action="store",
        help="finer control of verbosity (0 to 50); see also --debug")
    parser.add_argument(
        '--log-file',
        metavar="file", action='store',
        default=os.path.join(
            user_log_dir(APP_NAME, APP_AUTHOR[0]),
            '%s.log' % APP_NAME),
        help='where to save the log; a single - will disable it.')
    parser.add_argument(
        "--version", default=False,
        action="store_true",
        help="print program version and exit")

    return parser


def setup_logging(args):
    """
     Prepares our logging mechanism.

    :param args: Arguments returned by the parser
    :return: True if all went well, False to exit with error
    """
    from taco.constants import APP_NAME, APP_VERSION, APP_STAGE
    logger = logging.getLogger('')

    # Determine the level of logging.
    if args.log_level == logging.INFO:
        log_level = logging.DEBUG if args.verbose else logging.INFO
    else:
        try:
            log_level = int(args.log_level)
            if (log_level < 0) or (log_level > logging.CRITICAL):
                raise ValueError
        except ValueError:
            print("ERROR! --log-level expects an integer between 1 and %d" %
                  logging.CRITICAL)
            return False

    # The format we're going to use in all handlers.
    fmt = logging.Formatter(
        "[%(levelname)s] %(asctime)s %(filename)s:%(lineno)d "
        "[%(funcName)s] %(message)s",
        '%Y-%m-%d %H:%M:%S')

    # This is the console output.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    # This is the file output.
    if len(args.log_file) > 0 and args.log_file != '-':
        file_path, file_name = os.path.split(args.log_file)
        if not os.path.isdir(file_path):
            os.makedirs(file_path)
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(fmt)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)

    logger.setLevel(log_level)
    logger.info(
        "%s v%.1f %s STARTED", APP_NAME, APP_VERSION, APP_STAGE)
    logger.debug("logging to %s", args.log_file)
    return True


def main():
    """
    Entry point for the application.
    """

    # Initialize random numbers generator.
    random.seed(datetime.now())

    # deal with arguments
    parser = make_argument_parser()
    args = parser.parse_args()
    args.parser = parser

    # Deal with special cases.
    if args.version:
        from taco.constants import APP_NAME, APP_VERSION, APP_STAGE
        print("%s v%.1f %s" % (APP_NAME, APP_VERSION, APP_STAGE))
        return 0

    # Handle signals.
    from taco.globals import properexit
    signal.signal(signal.SIGINT, properexit)

    # Prepare the logger.
    if not setup_logging(args):
        return 1

    import taco.routes
    import taco.server
    import taco.clients
    import taco.crypto
    import taco.settings
    import taco.filesystem
    import taco.limiter
    import taco.globals

    taco.constants.JSON_SETTINGS_FILENAME = args.config_file

    taco.settings.Load_Settings()
    taco.crypto.Init_Local_Crypto()

    taco.globals.upload_limiter = taco.limiter.Speedometer()
    taco.globals.download_limiter = taco.limiter.Speedometer()

    taco.globals.server = taco.server.TacoServer()
    taco.globals.server.start()

    taco.globals.clients = taco.clients.TacoClients()
    taco.globals.clients.start()

    taco.globals.filesys = taco.filesystem.TacoFilesystemManager()
    taco.globals.filesys.start()

    from taco.bottle import run
    run(
        host=taco.globals.settings["Web IP"],
        port=int(taco.globals.settings["Web Port"]),
        reloader=False,
        quiet=True,
        debug=True,
        server="cherrypy")


if __name__ == '__main__':
    sys.exit(main())
