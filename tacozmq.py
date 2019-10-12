#!/usr/bin/env python

"""
TacoDARKNET: darknet written in python and zeromq

Author: Scott Powers
"""

import sys
import argparse
import zmq
import logging
import signal

import taco.constants

if zmq.zmq_version_info() < (4, 0):
    raise RuntimeError("Security is not supported in libzmq version < 4.0. "
                       "libzmq version {0}".format(zmq.zmq_version()))
if sys.version_info < (2, 7):
    raise RuntimeError("must use python 2.7 or greater")

parser = argparse.ArgumentParser(
    description='TacoZMQ: a darknet written in python and zeromq')
parser.add_argument(
    '--config', default=taco.constants.JSON_SETTINGS_FILENAME,
    dest='configfile',
    help='specify the location of the config json')
parser.add_argument(
    "--verbose", default=False,
    dest="verbose", action="store_true",
    help="increase output verbosity")
args = parser.parse_args()

taco.constants.JSON_SETTINGS_FILENAME = args.configfile

level = logging.INFO
if args.verbose:
    level = logging.DEBUG
logging.basicConfig(
    level=level,
    format="[%(levelname)s]\t[%(asctime)s] [%(filename)s:%(lineno)d] "
           "[%(funcName)s] %(message)s")

import taco.bottle
import taco.routes
import taco.server
import taco.clients
import taco.crypto
import taco.settings
import taco.filesystem
import taco.limiter
import taco.globals

signal.signal(signal.SIGINT, taco.globals.properexit)


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

taco.bottle.run(
    host=taco.globals.settings["Web IP"],
    port=int(taco.globals.settings["Web Port"]),
    reloader=False,
    quiet=True,
    debug=True,
    server="cherrypy")
