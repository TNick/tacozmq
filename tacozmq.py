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

    parser = argparse.ArgumentParser(
        description='TacoZMQ: a darknet written in python and zeromq')
    parser.add_argument(
        '--config', default=get_config_file(),
        dest='configfile',
        help='specify the location of the config file')
    parser.add_argument(
        "--verbose", default=False,
        dest="verbose", action="store_true",
        help="increase output verbosity")
    parser.add_argument(
        "--version", default=False,
        dest="version", action="store_true",
        help="print program version and exit")
    return parser



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

    import taco.routes
    import taco.server
    import taco.clients
    import taco.crypto
    import taco.settings
    import taco.filesystem
    import taco.limiter
    import taco.globals

    # Deal with special cases.
    if args.version:
        print("%s v%.1f %s" % (
            taco.constants.APP_NAME, taco.constants.APP_VERSION,
            taco.constants.APP_STAGE))
        return 0

    signal.signal(signal.SIGINT, taco.globals.properexit)

    taco.constants.JSON_SETTINGS_FILENAME = args.configfile

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="[%(levelname)s]\t[%(asctime)s] [%(filename)s:%(lineno)d] "
               "[%(funcName)s] %(message)s")


    logging.info(
        "%s v%.1f %s STARTED", taco.constants.APP_NAME,
        taco.constants.APP_VERSION, taco.constants.APP_STAGE)
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

    logging.info(
        "Starting Local Webserver on %s:%r",
        taco.globals.settings["Web IP"], taco.globals.settings["Web Port"])
    logging.info("*** %s Running ***", taco.constants.APP_NAME)

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
