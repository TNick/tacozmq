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

from taco.constants import KEY_GENERATION_PREFIX, KEY_SERVER_SECRET_SUFFIX
from .utils import event_monitor, norm_join
from .constants import TRACE, NO_IDENTITY


logger = logging.getLogger('tacozmq.server')


class TacoServer(threading.Thread):
    """
    A thread that manages our reply server.

    This is a "server" according to the
    [zmq_curve](http://api.zeromq.org/4-1:zmq-curve) which states that:
    > A socket using CURVE can be either client or server,
    > at any moment, but not both.
    > The role is independent of bind/connect direction.

    To become a CURVE server, the application sets the ZMQ_CURVE_SERVER
    option on the socket, and then sets the ZMQ_CURVE_SECRETKEY option
    to provide the socket with its long-term secret key.
    The application does not provide the socket with its long-term public key,
    which is used only by clients.

    """
    def __init__(self, app, bind_ip, bind_port):
        """
        Constructor.

        :param app: The application instance where this belongs.
        :param bind_ip: Address to bind to.
        :param bind_port: Port to bind to.
        """
        logger.debug('server %r:%r is being constructed...',
                     bind_ip, bind_port)
        threading.Thread.__init__(self, name="thTacoServer")
        self.app = app

        # TODO: in current implementation this may be None
        # as this only gets the parameters from command line.
        # If there were no parameters then - at start of thread -
        # these are read from settings. I see no reason for delaying this.
        self.bind_ip = bind_ip
        self.bind_port = bind_port

        # Set this to terminate the thread.
        self.stop = threading.Event()

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1

        self.client_last_request_time = {}
        self.client_last_request_time_lock = threading.Lock()

        # We keep an integer in settings that tracks the number of times
        # the settings were saved. Inhere we store the value of that
        # integer last time we inspected the settings and we use
        # settings_changed() whn we see a discrepancy.
        self.settings_trace_number = 1

        self.server_ctx = None
        self.server_auth = None
        self.socket = None
        logger.debug('server constructed')

    def create(self):
        """ Called from run() to initialize the state at thread startup. """
        self.set_status("Server Startup")

        self.set_status("Creating zmq Context", logging.DEBUG)
        self.server_ctx = zmq.Context()

        with self.app.settings_lock:
            if self.bind_ip is None:
                self.bind_ip = self.app.settings["Application IP"]
            if self.bind_port is None:
                self.bind_port = self.app.settings["Application Port"]
            public_dir = self.app.public_dir
            private_dir = self.app.private_dir

        self.set_status("Creating Server Context...", logging.DEBUG)

        # The REP socket type acts as as service for a set of client peers,
        # receiving requests and sending replies back to the requesting
        # peers. It is designed for simple remote-procedure call models.
        # https://rfc.zeromq.org/spec:28/REQREP/#the-rep-socket-type
        socket = self.server_ctx.socket(zmq.REP)

        # Do not keep messages in memory that were not send yet when
        # we attempt to close the socket.
        # http://api.zeromq.org/2-1:zmq-setsockopt#toc15
        socket.setsockopt(zmq.LINGER, 0)

        if not self.app.no_encryption:
            self.set_status("Starting zmq ThreadedAuthenticator",
                            logging.DEBUG)
            self.server_auth = ThreadAuthenticator(
                self.server_ctx, log=logging.getLogger('tacozmq.s_auth'))
            self.server_auth.start()
            self.server_auth.thread.name = "thTacoServerAuth"

            self.set_status(
                "Configuring Curve to use public key dir: %s" % public_dir)
            self.server_auth.configure_curve(domain='*', location=public_dir)

            self.set_status("Loading Server Certs...", logging.DEBUG)
            server_public, server_secret = zmq.auth.load_certificate(
                norm_join(private_dir,
                          '%s-%s' % (
                              KEY_GENERATION_PREFIX,
                              KEY_SERVER_SECRET_SUFFIX)))

            # To become a CURVE server, the application sets the ZMQ_CURVE_SERVER
            # option on the socket,
            socket.curve_server = True

            # and then sets the ZMQ_CURVE_SECRETKEY option
            # to provide the socket with its long-term secret key.
            socket.curve_secretkey = server_secret

            # The application does not provide the socket with
            # its long-term public key, which is used only by clients.
            # socket.curve_publickey = server_public

        if self.bind_ip == "0.0.0.0":
            self.bind_ip = "*"
        address = "tcp://%s:%d" % (self.bind_ip, self.bind_port)
        self.set_status("Server is now listening for encrypted "
                        "ZMQ connections @ %s" % address)
        socket.bind(address)

        # We can enable monitoring at zmq level.
        if self.app.zmq_monitor:
            t = threading.Thread(
                name = "thTacoSeMon",
                target=event_monitor,
                args=(socket.get_monitor_socket(),))
            t.start()

        self.socket = socket
        logger.debug("created")

    def terminate(self):
        """ Called from run() to terminat the state at thread finish. """
        self.set_status("Stopping zmq server with 0 second linger")
        self.socket.close(0)
        self.socket = None
        self.set_status("Stopping zmq ThreadedAuthenticator")
        if self.server_auth is not None:
            self.server_auth.stop()
            self.server_auth = None
        self.server_ctx.term()
        self.server_ctx = None
        self.set_status("Server Exit")

    def run(self):
        self.create()
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN | zmq.POLLOUT)

        while not self.stop.is_set():
            reply = ""
            try:
                socks = dict(poller.poll(200))
            except zmq.ZMQError:
                logger.error("Error while polling sockets", exc_info=True)
                socks = {}
            logger.log(TRACE, 'cycle start with %d active sockets', len(socks))

            # Check if settings changed and update accordingly.
            # We use this mechanism because, if keys are added / removed,
            # the ThreadAuthenticator would not notice
            # (configure_curve needs to be called again).
            if self.settings_trace_number != self.app.store.trace_number:
                self.settings_changed()

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

            try:
                socks = dict(poller.poll(10))
            except zmq.ZMQError:
                logger.error("Error while polling sockets", exc_info=True)
                socks = {}

            if self.socket in socks and socks[self.socket] == zmq.POLLOUT:
                logger.log(TRACE, 'responding to client_uuid %s', client_uuid)
                with self.app.upload_limiter_lock:
                    self.app.upload_limiter.add(len(reply))
                self.socket.send(reply)
            elif len(reply) > 0:
                logger.error(
                    'got reply <%r> to send but socket is in invalid state',
                    reply)

        self.terminate()

    def settings_changed(self):
        """ Called when we detect a change in settings. """
        self.settings_trace_number = self.app.store.trace_number

        if not self.app.no_encryption:
            with self.app.settings_lock:
                public_dir = self.app.public_dir
            self.set_status("Configuring Curve to use private key dir: %s" %
                            public_dir)
            # Certificates can be added and removed in directory at any time.
            # configure_curve must be called every time certificates are added
            # or removed, in order to update the Authenticator’s state.
            self.server_auth.configure_curve(domain='*', location=public_dir)

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

