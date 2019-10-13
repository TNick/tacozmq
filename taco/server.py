# -*- coding: utf-8 -*-
"""
This is the zmq server for the local machine.
"""
from __future__ import unicode_literals
from __future__ import print_function

import threading
import logging
import time
import zmq
from zmq.auth.thread import ThreadAuthenticator
import os

from taco.constants import KEY_GENERATION_PREFIX
from taco.utils import norm_path


class TacoServer(threading.Thread):
    def __init__(self, app, bind_ip, bind_port):
        threading.Thread.__init__(self)
        self.app = app
        self.bind_ip = bind_ip
        self.bind_port = bind_port

        self.stop = threading.Event()

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1

        self.client_last_request_time = {}
        self.client_last_request_time_lock = threading.Lock()

    def set_client_last_request(self, peer_uuid):
        # self.set_status("Server has serviced a request from:" + peer_uuid)
        with self.client_last_request_time_lock:
            self.client_last_request_time[peer_uuid] = time.time()

    def get_client_last_request(self, peer_uuid):
        with self.client_last_request_time_lock:
            if peer_uuid in self.client_last_request_time:
                return self.client_last_request_time[peer_uuid]
        return -1

    def set_status(self, text, level=0):
        if level == 0:
            logging.info(text)
        elif level == 1:
            logging.debug(text)
        with self.status_lock:
            self.status = text
            self.status_time = time.time()

    def get_status(self):
        with self.status_lock:
            return self.status, self.status_time

    def run(self):
        self.set_status("Server Startup")

        self.set_status("Creating zmq Contexts", 1)
        serverctx = zmq.Context()

        self.set_status("Starting zmq ThreadedAuthenticator", 1)
        # serverauth = zmq.auth.ThreadedAuthenticator(serverctx)
        serverauth = ThreadAuthenticator(serverctx)
        serverauth.start()

        with self.app.settings_lock:
            if self.bind_ip is None:
                self.bind_ip = self.app.settings["Application IP"]
            if self.bind_port is None:
                self.bind_port = self.app.settings["Application Port"]

            localuuid = self.app.settings["Local UUID"]
            publicdir = norm_path(
                self.app.settings["TacoNET Certificates Store"] + "/" + self.app.settings[
                    "Local UUID"] + "/public/")
            privatedir = norm_path(
                self.app.settings["TacoNET Certificates Store"] + "/" + self.app.settings[
                    "Local UUID"] + "/private/")

        self.set_status("Configuring Curve to use publickey dir:" + publicdir)
        serverauth.configure_curve(domain='*', location=publicdir)
        # auth.configure_curve(domain='*', location=zmq.auth.CURVE_ALLOW_ANY)

        self.set_status("Creating Server Context", 1)
        server = serverctx.socket(zmq.REP)
        server.setsockopt(zmq.LINGER, 0)

        self.set_status("Loading Server Certs", 1)
        server_public, server_secret = zmq.auth.load_certificate(os.path.normpath(
            os.path.abspath(privatedir + "/" + KEY_GENERATION_PREFIX + "-server.key_secret")))
        server.curve_secretkey = server_secret
        server.curve_publickey = server_public

        server.curve_server = True
        if self.bind_ip == "0.0.0.0":
            self.bind_ip = "*"
        address = "tcp://%s:%d" % (self.bind_ip, self.bind_port)
        self.set_status("Server is now listening for encrypted "
                        "ZMQ connections @ %s" % address)
        server.bind(address)

        poller = zmq.Poller()
        poller.register(server, zmq.POLLIN | zmq.POLLOUT)

        while not self.stop.is_set():
            reply = ""
            socks = dict(poller.poll(200))
            if server in socks and socks[server] == zmq.POLLIN:
                # self.set_status("Getting a request")
                data = server.recv()
                with self.app.download_limiter_lock:
                    self.app.download_limiter.add(len(data))
                (client_uuid, reply) = self.app.commands.Proccess_Request(data)
                if client_uuid != "0":
                    self.set_client_last_request(client_uuid)

            socks = dict(poller.poll(10))
            if server in socks and socks[server] == zmq.POLLOUT:
                # self.set_status("Replying to a request")
                with self.app.upload_limiter_lock:
                    self.app.upload_limiter.add(len(reply))
                server.send(reply)

        self.set_status("Stopping zmq server with 0 second linger")
        server.close(0)
        self.set_status("Stopping zmq ThreadedAuthenticator")
        serverauth.stop()
        serverctx.term()
        self.set_status("Server Exit")
