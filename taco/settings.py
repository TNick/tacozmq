# -*- coding: utf-8 -*-
"""
Application settings.
"""
from __future__ import unicode_literals
from __future__ import print_function

import os
import json
import logging
import time

from taco.constants import JSON_SETTINGS_FILENAME, APP_NAME
import taco.defaults
from taco.utils import norm_join, norm_path


class TacoSettings(object):
    def __init__(self, app):
        super(TacoSettings, self).__init__()
        self.app = app

    def Load_Settings(self, needlock=True):
        logging.debug("loading settings ...")
        save_after = False
        if needlock:
            self.app.settings_lock.acquire()

        try:
            try:
                logging.debug("Loading Settings JSON")
                with open(JSON_SETTINGS_FILENAME, 'r') as fin:
                    self.app.settings = json.load(fin)
            except Exception:
                self.app.settings = {"Peers": {}, "Shares": []}

            logging.debug("Verifying the settings loaded from the json "
                          "isn't missing any required keys")
            for keyname in taco.defaults.default_settings_kv.keys():
                if not keyname in self.app.settings:
                    self.app.settings[keyname] = \
                        taco.defaults.default_settings_kv[keyname]
                    save_after = True

            if not os.path.isdir(self.app.settings["TacoNET Certificates Store"]):
                logging.debug("Making %s Certificates Store", APP_NAME)
                os.makedirs(self.app.settings["TacoNET Certificates Store"])

            logging.debug("Verifying settings share list is in correct format")
            if not isinstance(self.app.settings["Shares"], list):
                self.app.shares = []
                save_after = True

            logging.debug("Verifying settings peer dict is in correct format")
            keep_keys = []
            for peer_uuid in self.app.settings["Peers"].keys():
                peer_data = self.app.settings["Peers"][peer_uuid]
                if peer_data["enabled"]:
                    self.Enable_Key(
                        peer_uuid, "client", peer_data["clientkey"], False)
                    self.Enable_Key(
                        peer_uuid, "server", peer_data["serverkey"], False)
                    keep_keys.append(peer_uuid + "-client.key")
                    keep_keys.append(peer_uuid + "-server.key")
            self.Disable_Keys(keep_keys, False)

        finally:
            if needlock:
                self.app.settings_lock.release()

        logging.debug("settings loaded")
        if save_after:
            self.Save_Settings()

    def Save_Settings(self, needlock=True):
        logging.debug("saving settings...")
        if needlock:
            self.app.settings_lock.acquire()
        try:
            with open(JSON_SETTINGS_FILENAME, 'w') as fout:
                json.dump(self.app.settings, fout, indent=4, sort_keys=True)
        finally:
            if needlock:
                self.app.settings_lock.release()
        logging.debug("settings saved")
        self.Load_Settings(needlock)

    def Disable_Keys(self, keys_to_keep, needlock=True):
        logging.debug("Disabling Peer Keys if Needed")
        if needlock:
            self.app.settings_lock.acquire()
        try:
            public_dir = norm_join(
                self.app.settings["TacoNET Certificates Store"],
                self.app.settings["Local UUID"],
                "public"
            )
        finally:
            if needlock:
                self.app.settings_lock.release()

        if not os.path.exists(public_dir):
            os.makedirs(public_dir)
        filelisting = os.listdir(norm_path(public_dir))
        delete_files = []
        logging.debug("Keys that will be kept: " + str(keys_to_keep))
        for filename in filelisting:
            if filename not in keys_to_keep:
                delete_files.append(filename)

        for file_to_delete in delete_files:
            logging.info("Deleting key: " + file_to_delete)
            full_path = norm_join(public_dir, file_to_delete)
            if os.path.isfile(full_path):
                os.remove(full_path)

    def Enable_Key(self, peer_uuid, key_type, key_string, needlock):
        logging.info("Enabling KEY for UUID:%s -- %s -- %s",
                     peer_uuid, key_type, key_string)
        template = (
            "\n"
            "#   **** Saved on %s by tacozmq  ****\n"
            "#   for peer: %s\n"
            "#   type: %s\n"
            "#   ZeroMQ CURVE Public Certificate\n"
            "#   Exchange securely, or use a secure mechanism to verify the contents\n"
            "#   of this file after exchange. Store public certificates in your home\n"
            "#   directory, in the .curve subdirectory.\n"
            "\n"
            "metadata\n"
            "curve\n"
            "    public-key = \"%s\"\n"
            "  ")

        if needlock:
            self.app.settings_lock.acquire()
        public_dir = norm_join(
            self.app.settings["TacoNET Certificates Store"],
            self.app.settings["Local UUID"],
            "public")
        if needlock:
            self.app.settings_lock.release()
        location = norm_join(
            public_dir, '%s-%s.key' % (peer_uuid, key_type))

        template_out = template % (
            str(time.time()), peer_uuid, key_type, key_string)
        if not os.path.isdir(public_dir):
            os.makedirs(public_dir)
        with open(location, 'w') as fout:
            fout.write(template_out)
