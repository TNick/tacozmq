# -*- coding: utf-8 -*-
"""
Hosts our top level class representing a full application.
"""
from __future__ import unicode_literals
from __future__ import print_function

import threading
import taco.constants
import logging
import os
import uuid


class TacoApp(object):
    """
    Our application.

    While transitioning from module-level variables we use an instance
    variable that stores the last object of this class to be created.
    Currently it is mostly used in routes.py and apis.py.
    """
    instance = None

    settings_lock = threading.Lock()
    settings = {}

    chat_log = []
    chat_log_lock = threading.Lock()

    chat_uuid = uuid.uuid4().hex
    chat_uuid_lock = threading.Lock()

    stop = threading.Event()

    public_keys_lock = threading.Lock()
    public_keys = {}

    share_listings_i_care_about = {}
    share_listings_i_care_about_lock = threading.Lock()

    share_listing_requests_lock = threading.Lock()
    share_listing_requests = {}

    share_listings = {}
    share_listings_lock = threading.Lock()

    download_q = {}
    download_q_lock = threading.Lock()

    completed_q = []
    completed_q_lock = threading.Lock()

    upload_q = {}
    upload_q_lock = threading.Lock()

    upload_limiter_lock = threading.Lock()
    download_limiter_lock = threading.Lock()

    high_priority_output_queue_lock = threading.Lock()
    medium_priority_output_queue_lock = threading.Lock()
    low_priority_output_queue_lock = threading.Lock()
    file_request_output_queue_lock = threading.Lock()

    high_priority_output_queue = {}
    medium_priority_output_queue = {}
    low_priority_output_queue = {}
    file_request_output_queue = {}

    def __init__(self):
        super(TacoApp, self).__init__()
        TacoApp.instance = self

        from taco.settings import TacoSettings
        self.store = TacoSettings(self)
        self.store.Load_Settings()

        from taco.crypto import Init_Local_Crypto
        Init_Local_Crypto(self)

        from taco.limiter import Speedometer
        self.upload_limiter = Speedometer()
        self.download_limiter = Speedometer()

        from taco.server import TacoServer
        self.server = TacoServer(self)
        self.server.start()

        from taco.clients import TacoClients
        self.clients = TacoClients(self)
        self.clients.start()

        from taco.filesystem import TacoFilesystemManager
        self.filesys = TacoFilesystemManager(self)
        self.filesys.start()

        from taco.commands import TacoCommands
        self.commands = TacoCommands(self)

    def start(self):
        """ Starts the application. """
        from taco.bottle import run
        run(
            host=self.settings["Web IP"],
            port=int(self.settings["Web Port"]),
            reloader=False,
            quiet=True,
            debug=True,
            server="cherrypy")

    def restart(self):
        """ Recreates the client and the server. """
        self.server.stop.set()
        self.clients.stop.set()
        self.server.join()
        self.clients.join()
        from taco.server import TacoServer
        self.server = TacoServer(self)
        from taco.clients import TacoClients
        self.clients = TacoClients(self)
        self.server.start()
        self.clients.start()

    def Add_To_Output_Queue(self, peer_uuid, msg, priority=3):
        logging.debug("Add to " + peer_uuid + " output q @ " + str(priority))
        if priority == 1:
            with self.high_priority_output_queue_lock:
                if peer_uuid in self.high_priority_output_queue:
                    self.high_priority_output_queue[peer_uuid].put(msg)
                    self.clients.sleep.set()
                    return 1
        elif priority == 2:
            with self.medium_priority_output_queue_lock:
                if peer_uuid in self.medium_priority_output_queue:
                    self.medium_priority_output_queue[peer_uuid].put(msg)
                    self.clients.sleep.set()
                    return 1
        elif priority == 3:
            with self.low_priority_output_queue_lock:
                if peer_uuid in self.low_priority_output_queue:
                    self.low_priority_output_queue[peer_uuid].put(msg)
                    self.clients.sleep.set()
                    return 1
        else:
            with self.file_request_output_queue_lock:
                if peer_uuid in self.file_request_output_queue:
                    self.file_request_output_queue[peer_uuid].put(msg)
                    self.clients.sleep.set()
                    return 1

        return 0

    def Add_To_All_Output_Queues(self, msg, priority=3):
        logging.debug("Add to ALL output q @ " + str(priority))
        if priority == 1:
            with self.high_priority_output_queue_lock:
                for key_name in self.high_priority_output_queue:
                    self.high_priority_output_queue[key_name].put(msg)
                    self.clients.sleep.set()
                return 1
        elif priority == 2:
            with self.medium_priority_output_queue_lock:
                for key_name in self.medium_priority_output_queue:
                    self.medium_priority_output_queue[key_name].put(msg)
                    self.clients.sleep.set()
                return 1
        elif priority == 3:
            with self.low_priority_output_queue_lock:
                for key_name in self.low_priority_output_queue:
                    self.low_priority_output_queue[key_name].put(msg)
                    self.clients.sleep.set()
                return 1
        else:
            with self.file_request_output_queue_lock:
                for key_name in self.file_request_output_queue:
                    self.file_request_output_queue[key_name].put(msg)
                    self.clients.sleep.set()
                    return 1

        return 0

    def proper_exit(self, signum, frame):
        self.stop.set()
        logging.info("Stopping Server")
        self.server.stop.set()
        logging.info("Stopping Clients")
        self.clients.stop.set()
        self.clients.sleep.set()
        logging.info("Stopping Filesystem Workers")
        self.filesys.stop.set()
        self.filesys.sleep.set()
        self.server.join()
        self.clients.join()
        self.filesys.join()
        logging.debug("Dispatcher Stopped Successfully")
        logging.info("Clean Exit")


def proper_exit(signum, frame):
    """ Signal handler. """
    logging.warning("SIGINT Detected, stopping " + taco.constants.APP_NAME)
    app = TacoApp.instance
    if app is not None:
        app.proper_exit(signum, frame)
    import sys
    sys.exit(3)
