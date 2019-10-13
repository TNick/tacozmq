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


def Init_Local_Crypto(app):
    logging.debug("Started")
    with app.settings_lock:
        workingdir = app.settings["TacoNET Certificates Store"]
        privatedir = norm_path(
            app.settings["TacoNET Certificates Store"] + "/" + app.settings[
                "Local UUID"] + "/private/")
        publicdir = norm_path(
            app.settings["TacoNET Certificates Store"] + "/" + app.settings[
                "Local UUID"] + "/public/")

    if not os.path.isdir(privatedir):
        os.makedirs(privatedir)
    if not os.path.isdir(publicdir):
        os.makedirs(publicdir)

    server_cert = norm_join(privatedir,
                            KEY_GENERATION_PREFIX + "-server.key")
    server_key = norm_join(privatedir,
                           KEY_GENERATION_PREFIX + "-server.key_secret")
    server_generate = not (isfile(server_cert) and isfile(server_key))

    client_cert = norm_join(privatedir,
                            KEY_GENERATION_PREFIX + "-client.key")
    client_key = norm_join(privatedir,
                           KEY_GENERATION_PREFIX + "-client.key_secret")
    client_generate = not (isfile(client_cert) and isfile(client_key))

    if server_generate:
        logging.info("Server CURVE Public or Private Key Missing, Generating")
        server_public_file, server_secret_file = zmq.auth.create_certificates(
            workingdir,
            KEY_GENERATION_PREFIX + "-server")
        shutil.move(norm_path(server_public_file), norm_path(privatedir))
        shutil.move(norm_path(server_secret_file), norm_path(privatedir))
    if client_generate:
        logging.info("Client CURVE Public or Private Key Missing, Generating")
        client_public_file, client_secret_file = zmq.auth.create_certificates(
            workingdir,
            KEY_GENERATION_PREFIX + "-client")
        shutil.move(norm_path(client_public_file), norm_path(privatedir))
        shutil.move(norm_path(client_secret_file), norm_path(privatedir))

    logging.debug("Getting keys into globals")

    with open(client_cert, 'r') as fin:
        client_public_key = s = fin.read()
    with open(server_cert, 'r') as fin:
        server_public_key = s = fin.read()

    with app.public_keys_lock:
        data = re.search(r'.*public-key = "(.+)"',
                         client_public_key, re.MULTILINE)
        assert data
        app.public_keys["client"] = data.group(1)

        data = re.search(r'.*public-key = "(.+)"',
                         server_public_key, re.MULTILINE)
        assert data
        app.public_keys["server"] = data.group(1)

    logging.debug("Finished")
