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
from taco.utils import norm_path, norm_join

from .constants import TRACE, NO_IDENTITY

logger = logging.getLogger('tacozmq.server')


class TacoServer(threading.Thread):
    def __init__(self, app, bind_ip, bind_port):
        logger.debug('server %r:%r is being constructed...',
                     bind_ip, bind_port)
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

        self.server_ctx = None
        self.server_auth = None
        self.socket = None
        logger.debug('server constructed')

    def set_client_last_request(self, peer_uuid):
        logger.log(TRACE, 'server has serviced a request from: %s', peer_uuid)
        with self.client_last_request_time_lock:
            self.client_last_request_time[peer_uuid] = time.time()

    def get_client_last_request(self, peer_uuid):
        with self.client_last_request_time_lock:
            if peer_uuid in self.client_last_request_time:
                return self.client_last_request_time[peer_uuid]
        return -1

    def set_status(self, text, level=logging.INFO):
        logger.log(level, text)
        with self.status_lock:
            self.status = text
            self.status_time = time.time()

    def get_status(self):
        with self.status_lock:
            return self.status, self.status_time

    def create(self):
        """ Called from run() to initialize the state at thread startup. """
        self.set_status("Server Startup")

        self.set_status("Creating zmq Context", logging.DEBUG)
        self.server_ctx = zmq.Context()

        self.set_status("Starting zmq ThreadedAuthenticator", logging.DEBUG)
        self.server_auth = ThreadAuthenticator(self.server_ctx)
        self.server_auth.start()

        with self.app.settings_lock:
            if self.bind_ip is None:
                self.bind_ip = self.app.settings["Application IP"]
            if self.bind_port is None:
                self.bind_port = self.app.settings["Application Port"]
            local_uuid = self.app.settings["Local UUID"]
            store_path = self.app.settings["TacoNET Certificates Store"]
        public_dir = norm_join(store_path, local_uuid, "public")
        private_dir = norm_join(store_path, local_uuid, "private")

        self.set_status(
            "Configuring Curve to use public key dir:" + public_dir)
        self.server_auth.configure_curve(domain='*', location=private_dir)

        self.set_status("Creating Server Context...", logging.DEBUG)
        socket = self.server_ctx.socket(zmq.REP)
        socket.setsockopt(zmq.LINGER, 0)

        self.set_status("Loading Server Certs...", logging.DEBUG)
        server_public, server_secret = zmq.auth.load_certificate(
            norm_join(private_dir,
                      KEY_GENERATION_PREFIX + "-server.key_secret"))
        socket.curve_secretkey = server_secret
        socket.curve_publickey = server_public

        socket.curve_server = True
        if self.bind_ip == "0.0.0.0":
            self.bind_ip = "*"
        address = "tcp://%s:%d" % (self.bind_ip, self.bind_port)
        self.set_status("Server is now listening for encrypted "
                        "ZMQ connections @ %s" % address)
        socket.bind(address)
        self.socket = socket
        logger.debug("created")

    def terminate(self):
        """ Called from run() to terminat the state at thread finish. """
        self.set_status("Stopping zmq server with 0 second linger")
        self.socket.close(0)
        self.set_status("Stopping zmq ThreadedAuthenticator")
        self.server_auth.stop()
        self.server_ctx.term()
        self.set_status("Server Exit")
        self.server_ctx = None
        self.server_auth = None
        self.socket = None
        logger.debug("terminated")

    def run(self):
        self.create()

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN | zmq.POLLOUT)

        while not self.stop.is_set():
            reply = ""
            socks = dict(poller.poll(200))
            logger.log(TRACE, 'cycle start with %d active sockets', len(socks))

            if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                data = self.socket.recv()
                logger.log(TRACE, 'active request with %d bytes', len(data))
                with self.app.download_limiter_lock:
                    self.app.download_limiter.add(len(data))
                (client_uuid, reply) = self.app.commands.process_request(data)
                logger.log(TRACE, 'response to client_uuid %s has %d bytes',
                           client_uuid, len(reply))
                if client_uuid != NO_IDENTITY:
                    self.set_client_last_request(client_uuid)

            socks = dict(poller.poll(10))
            if self.socket in socks and socks[self.socket] == zmq.POLLOUT:
                logger.log(TRACE, 'responding to client_uuid %s', client_uuid)
                with self.app.upload_limiter_lock:
                    self.app.upload_limiter.add(len(reply))
                self.socket.send(reply)
            elif len(reply) > 0:
                logger.debug(
                    'got reply <%r> to send but socket is in invalid state',
                    reply)

        self.terminate()
