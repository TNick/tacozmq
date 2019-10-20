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

from taco.constants import (
    JSON_SETTINGS_FILENAME, APP_NAME,
    KEY_CLIENT_PUBLIC_SUFFIX, KEY_SERVER_PUBLIC_SUFFIX, TRACE)
import taco.defaults
from taco.utils import norm_join, norm_path

logger = logging.getLogger('tacozmq.cmd')


class TacoSettings(object):
    def __init__(self, app):
        super(TacoSettings, self).__init__()
        self.app = app
        self.trace_number = 1

    def read(self):
        """ Reads the content of the file into this class instance. """
        try:
            logger.debug("Loading Settings JSON")
            with open(JSON_SETTINGS_FILENAME, 'r') as fin:
                self.app.settings = json.load(fin)
        except FileNotFoundError:
            logger.debug("Settings file does not exist")
        except (IOError, PermissionError):
            logger.error("Cannot open settings file", exc_info=True)
        except json.decoder.JSONDecodeError:
            logger.error("The file is not a proper json file",
                         exc_info=True)
        finally:
            if self.app.settings is None:
                self.app.settings = {"Peers": {}, "Shares": []}

    def load(self, need_lock=True, save_after=True, read_file=True):
        """ Reads the settings file and validates its content. """
        logger.debug("loading settings ...")
        local_save_after = False
        if need_lock:
            self.app.settings_lock.acquire()

        try:
            if read_file:
                self.read()

            if logger.level <= TRACE:
                logger.log(
                    TRACE, "Settings content:\n%s" % '\n'.join(
                        ['%s: %r' % (key, self.app.settings[key])
                         for key in self.app.settings.keys()]))

            logger.debug("Verifying the settings loaded from the json "
                         "isn't missing any required keys")
            for key_name in taco.defaults.default_settings_kv.keys():
                if key_name not in self.app.settings:
                    self.app.settings[key_name] = \
                        taco.defaults.default_settings_kv[key_name]
                    local_save_after = True

            if not os.path.isdir(self.app.settings["TacoNET Certificates Store"]):
                logger.debug("Making %s Certificates Store", APP_NAME)
                os.makedirs(self.app.settings["TacoNET Certificates Store"])

            logger.debug("Verifying settings share list is in correct format")
            if not isinstance(self.app.settings["Shares"], list):
                self.app.shares = []
                local_save_after = True

            logger.debug("Verifying settings peer dict is in correct format")
            self.refresh_keys()

        finally:
            if need_lock:
                self.app.settings_lock.release()

        logger.debug("settings loaded")
        if local_save_after and save_after:
            self.save(load_after=False)

    def refresh_keys(self):
        logger.debug("certificate store content is being synchronized with "
                     "settings content ...")
        keep_keys = []
        for peer_uuid in self.app.settings["Peers"].keys():
            peer_data = self.app.settings["Peers"][peer_uuid]
            if peer_data["enabled"]:
                self.enable_key(
                    peer_uuid, "client", peer_data["clientkey"], False)
                self.enable_key(
                    peer_uuid, "server", peer_data["serverkey"], False)
                keep_keys.append('%s-%s' % (
                    peer_uuid, KEY_CLIENT_PUBLIC_SUFFIX))
                keep_keys.append('%s-%s' % (
                    peer_uuid, KEY_SERVER_PUBLIC_SUFFIX))
        self.disable_keys(keep_keys, False)
        logger.debug("certificate store content synchronized")

    def save(self, need_lock=True, load_after=True):
        """
        Saves the settings structure to file.

        The content of the file can then be reloaded.
        """
        logger.debug("saving settings...")
        if need_lock:
            self.app.settings_lock.acquire()
        try:
            with open(JSON_SETTINGS_FILENAME, 'w') as fout:
                json.dump(self.app.settings, fout, indent=4, sort_keys=True)
        finally:
            if need_lock:
                self.app.settings_lock.release()
        self.trace_number = self.trace_number + 1
        logger.debug("settings saved")
        if load_after:
            self.load(need_lock=need_lock, save_after=False, read_file=False)

    def disable_keys(self, keys_to_keep, need_lock=True):
        """ Deletes keys from certificate store (public directory) if they
        don't belong to an enabled peer. """
        logger.debug("disabling peer keys if needed...")
        if need_lock:
            self.app.settings_lock.acquire()

        try:
            public_dir = self.app.public_dir
        finally:
            if need_lock:
                self.app.settings_lock.release()

        if not os.path.exists(public_dir):
            os.makedirs(public_dir)

        file_listing = os.listdir(public_dir)
        delete_files = []
        logger.debug("keys that will be kept: %r", keys_to_keep)
        for file_name in file_listing:
            if file_name not in keys_to_keep:
                delete_files.append(file_name)
                full_path = norm_join(public_dir, file_name)
                logger.info("deleting key %s, file %s ", file_name, full_path)
                if os.path.isfile(full_path):
                    os.remove(full_path)

        logger.debug("done disabling peer keys")

    def enable_key(self, peer_uuid, key_type, key_string, need_lock):
        """ Creates key file in certificate store's public directory
        based on a template.

        The function basically puts the information in the format
        expected by CURVE. Apart from a timestamp, no processing is
        done on the input.
        """
        logger.info("enabling KEY for UUID:%s -- %s -- %s",
                    peer_uuid, key_type, key_string)
        template = (
            "\n"
            "#   **** Saved on %s by tacozmq  ****\n"
            "#   for peer: %s\n"
            "#   type: %s\n"
            "#   ZeroMQ CURVE Public Certificate\n"
            "#   Exchange securely, or use a secure mechanism "
            "to verify the contents\n"
            "#   of this file after exchange. Store public "
            "certificates in your home\n"
            "#   directory, in the .curve subdirectory.\n"
            "\n"
            "metadata\n"
            "curve\n"
            "    public-key = \"%s\"\n"
            "  ")

        if need_lock:
            self.app.settings_lock.acquire()
        public_dir = self.app.public_dir
        if need_lock:
            self.app.settings_lock.release()
        location = norm_join(
            public_dir, '%s-%s.key' % (peer_uuid, key_type))

        template_out = template % (
            str(time.time()), peer_uuid, key_type, key_string)
        if not os.path.isdir(public_dir):
            os.makedirs(public_dir)
        with open(location, 'w') as fout:
            fout.write(template_out)
        logger.debug("keys for peer %r enabled", peer_uuid)

