# -*- coding: utf-8 -*-
"""
Deals woith the CURVE keys used for secure communication..
"""
from __future__ import unicode_literals
from __future__ import print_function
from taco.constants import *

import os
import logging
import zmq.auth
import shutil
import re
from os.path import isfile

from taco.utils import norm_path, norm_join

logger = logging.getLogger('tacozmq.crypto')


def init_local_crypto(app):
    logger.debug("initializing local cryptographic keys...")
    with app.settings_lock:
        working_dir = app.settings["TacoNET Certificates Store"]
        private_dir = app.private_dir
        public_dir = app.public_dir

    if not os.path.isdir(private_dir):
        os.makedirs(private_dir)
    if not os.path.isdir(public_dir):
        os.makedirs(public_dir)

    server_cert = norm_join(private_dir,
                            '%s-%s' % (
                               KEY_GENERATION_PREFIX,
                               KEY_SERVER_PUBLIC_SUFFIX))
    server_key = norm_join(private_dir,
                           '%s-%s' % (
                               KEY_GENERATION_PREFIX,
                               KEY_SERVER_SECRET_SUFFIX))
    server_generate = not (isfile(server_cert) and isfile(server_key))

    client_cert = norm_join(private_dir,
                            '%s-%s' % (
                                KEY_GENERATION_PREFIX,
                                KEY_CLIENT_PUBLIC_SUFFIX))
    client_key = norm_join(private_dir,
                           '%s-%s' % (
                               KEY_GENERATION_PREFIX,
                               KEY_CLIENT_SECRET_SUFFIX))
    client_generate = not (isfile(client_cert) and isfile(client_key))

    if server_generate:
        logger.info("Server CURVE Public or Private Key Missing, Generating")
        server_public_file, server_secret_file = \
            zmq.auth.create_certificates(
                working_dir,
                KEY_GENERATION_PREFIX + "-server")
        shutil.move(norm_path(server_public_file), private_dir)
        shutil.move(norm_path(server_secret_file), private_dir)
    if client_generate:
        logger.info("Client CURVE Public or Private Key Missing, Generating")
        client_public_file, client_secret_file = \
            zmq.auth.create_certificates(
                working_dir,
                KEY_GENERATION_PREFIX + "-client")
        shutil.move(norm_path(client_public_file), private_dir)
        shutil.move(norm_path(client_secret_file), private_dir)

    logger.debug("getting cryptographic keys into globals...")

    with open(client_cert, 'r') as fin:
        client_public_key = fin.read()
    with open(server_cert, 'r') as fin:
        server_public_key = fin.read()

    with app.public_keys_lock:
        data = re.search(r'.*public-key = "(.+)"',
                         client_public_key, re.MULTILINE)
        assert data
        app.public_keys["client"] = data.group(1)

        data = re.search(r'.*public-key = "(.+)"',
                         server_public_key, re.MULTILINE)
        assert data
        app.public_keys["server"] = data.group(1)

    logger.debug("local cryptographic keys initialized")
