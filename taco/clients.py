# -*- coding: utf-8 -*-
"""
Code dealing with clients that connect to local server.
"""
from __future__ import unicode_literals
from __future__ import print_function

import threading
import logging
import time
import zmq
from zmq.auth.thread import ThreadAuthenticator
from socket import gethostbyname, gaierror
import sys
import random

from .constants import *
from .utils import norm_join, event_monitor
from taco.thread import TacoThread

if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue

logger = logging.getLogger('tacozmq.clients')


class Peer(object):
    """ Represents a single peer. """
    parent = None
    uuid = None
    socket = None
    next_rollcall = -1
    connect_time = time.time() + CLIENT_RECONNECT_MIN
    reconnect_mod = CLIENT_RECONNECT_MIN
    last_reply_time = -1
    timeout = time.time() + ROLLCALL_TIMEOUT

    def __init__(self, parent, uuid):
        self.parent = parent
        self.uuid = uuid

    def set_last_reply(self):
        """
        Whenever we receive a reply we update the status.

        The extra time to be added between unsuccessful connections
        is reset to minimum.

        A timeout is computed starting from current time (redundant
        as this is now + constant and we store now).
        """
        logger.log(TRACE, "got reply from %s", self.uuid)
        now = time.time()
        self.reconnect_mod = CLIENT_RECONNECT_MIN
        self.timeout = now + ROLLCALL_TIMEOUT

        with self.parent.client_last_reply_time_lock:
            self.last_reply_time = now

    def create_peer_socket(self, client_ctx,
                           peer_data, ip_of_client):
        """ Creates the socket, sets it up, creates queues for it and
        saves a reference in our list of clients. """
        app = self.parent.app

        # The DEALER socket type talks to a set of anonymous peers,
        # sending and receiving messages using round-robin algorithms.
        # It is reliable, insofar as it does not drop messages.
        # DEALER works as an asynchronous replacement for REQ, for
        # clients that talk to REP or ROUTER servers.
        # https://rfc.zeromq.org/spec:28/REQREP/#the-dealer-socket-type
        new_socket = client_ctx.socket(zmq.DEALER)

        # Do not keep messages in memory that were not send yet when
        # we attempt to close the socket.
        # http://api.zeromq.org/2-1:zmq-setsockopt#toc15
        new_socket.setsockopt(zmq.LINGER, 0)
        if not app.no_encryption:
            client_public, client_secret = zmq.auth.load_certificate(
                norm_join(self.parent.private_dir,
                          "%s-%s" % (
                              KEY_GENERATION_PREFIX,
                              KEY_CLIENT_SECRET_SUFFIX)))
            # http://api.zeromq.org/4-1:zmq-curve
            # To become a CURVE client, the application sets the
            # ZMQ_CURVE_SERVERKEY option with the long-term public key
            # of the server it intends to connect to, or accept
            # connections from, next.
            new_socket.curve_serverkey = \
                str(peer_data["serverkey"]).encode('ascii')

            # The application then sets the ZMQ_CURVE_PUBLICKEY and
            # ZMQ_CURVE_SECRETKEY options with its client long-term key pair.
            # Set long term secret key (for server)
            new_socket.curve_publickey = client_public
            new_socket.curve_secretkey = client_secret

        address_str = "tcp://%s:%d" % (ip_of_client, peer_data["port"])
        new_socket.connect(address_str)
        self.parent.set_status("Client for %s started at %s" % (
            self.uuid, address_str))
        self.next_rollcall = time.time()

        with app.high_priority_output_queue_lock:
            app.high_priority_output_queue[self.uuid] = Queue()
        with app.medium_priority_output_queue_lock:
            app.medium_priority_output_queue[self.uuid] = Queue()
        with app.low_priority_output_queue_lock:
            app.low_priority_output_queue[self.uuid] = Queue()
        with app.file_request_output_queue_lock:
            app.file_request_output_queue[self.uuid] = Queue()

        # If a timeout limit was not yet computed then compute one now.
        if self.timeout is None:
             self.timeout = self.next_rollcall + ROLLCALL_TIMEOUT

        # We can enable monitoring at zmq level.
        if app.zmq_monitor:
            t = threading.Thread(
                name = "thTacoClMon",
                target=event_monitor,
                args=(new_socket.get_monitor_socket(),))
            t.start()

        self.socket = new_socket
        return new_socket

    def perform(self, poller):
        """ Called for connected peers to do some work. """
        logger.log(TRACE, 'peer %s is being processed...', self.uuid)
        self.perform_high_priority()
        self.perform_medium_priority()
        self.perform_file_transaction()
        self.perform_low_priority()
        self.perform_rollcall()
        self.receive_block(poller)
        logger.log(TRACE, 'peer %s processed', self.uuid)

    def perform_high_priority(self):
        """ High priority queue processing. """
        app = self.parent.app
        with app.high_priority_output_queue_lock:
            try:
                queue = app.high_priority_output_queue[self.uuid]
            except KeyError:
                logger.log(TRACE, 'peer %r not in high_priority_output_queue',
                           self.uuid)
                return
            while not queue.empty():
                self.parent.set_status(
                    "high priority output q not empty:" + self.uuid)
                data = queue.get()
                self.socket.send_multipart([b'', data])
                self.parent.sleep.set()
                with app.upload_limiter_lock:
                    app.upload_limiter.add(len(data))

    def perform_medium_priority(self, ):
        """ Medium priority queue processing. """
        app = self.parent.app
        with app.medium_priority_output_queue_lock:
            try:
                queue = app.medium_priority_output_queue[self.uuid]
            except KeyError:
                logger.log(TRACE, 'peer %r not in medium_priority_output_queue',
                           self.uuid)
                return
            while not queue.empty():
                self.parent.set_status(
                    "medium priority output q not empty:" + self.uuid)
                data = queue.get()
                self.socket.send_multipart([b'', data])
                self.parent.sleep.set()
                with app.upload_limiter_lock:
                    app.upload_limiter.add(len(data))

    def perform_low_priority(self, ):
        """ Low priority queue processing. """
        app = self.parent.app
        with app.low_priority_output_queue_lock:
            try:
                queue = app.low_priority_output_queue[self.uuid]
            except KeyError:
                logger.log(TRACE, 'peer %r not in low_priority_output_queue',
                           self.uuid)
                return
            if not queue.empty():
                with app.upload_limiter_lock:
                    upload_rate = app.upload_limiter.get_rate()
                max_upload_rate = self.parent.max_upload_rate
                if upload_rate < max_upload_rate:
                    self.parent.set_status(
                        "low priority output q not empty+free bw:" + self.uuid)
                    data = queue.get()
                    self.socket.send_multipart([b'', data])
                    self.parent.sleep.set()
                    with app.upload_limiter_lock:
                        app.upload_limiter.add(len(data))
                else:
                    logger.log(TRACE, 'upload rate %d > max_upload_rate %d',
                               upload_rate, max_upload_rate)

    def perform_file_transaction(self, ):
        """ File request queue, aka the download throttle. """
        if time.time() < self.parent.file_request_time:
            logger.log(TRACE, 'not the time for file transfer, yet')
            return
        self.parent.file_request_time = time.time()

        app = self.parent.app
        with app.file_request_output_queue_lock:
            try:
                queue = app.file_request_output_queue[self.uuid]
            except KeyError:
                logger.log(TRACE, 'peer %r not in file_request_output_queue',
                           self.uuid)
                return
            if not queue.empty():
                with app.download_limiter_lock:
                    download_rate = app.download_limiter.get_rate()

                bw_percent = download_rate / self.parent.max_download_rate
                wait_time = self.parent.chunk_request_rate * bw_percent
                logger.log(TRACE, 'file transaction %f wait time %r',
                           bw_percent, wait_time)

                if wait_time > 0.01:
                    self.parent.file_request_time += wait_time

                max_download_rate = self.parent.max_download_rate
                if download_rate < max_download_rate:
                    self.parent.set_status(
                        "filereq output q not empty+free bw:" + self.uuid)
                    data = queue.get()
                    self.socket.send_multipart([b'', data])
                    self.parent.sleep.set()
                    with app.upload_limiter_lock:
                        app.upload_limiter.add(len(data))
                else:
                    logger.log(TRACE,
                               "download_rate %r > max_download_rate %r",
                               download_rate, max_download_rate)

    def perform_rollcall(self, ):
        """ Make sure the network is responsive. """
        if self.next_rollcall >= time.time():
            return
        if self.socket is None:
            return

        app = self.parent.app
        data = app.commands.request_rollcall_cmd()
        self.socket.send_multipart([b'', data])
        self.parent.sleep.set()
        with app.upload_limiter_lock:
            app.upload_limiter.add(len(data))
        expect_answer = \
            time.time() + random.randint(ROLLCALL_MIN, ROLLCALL_MAX)
        self.next_rollcall = expect_answer
        logger.log(TRACE, "hart-beat send to peer %s; "
                          "expected to answer until %r",
                   self.uuid, expect_answer)

    def receive_block(self, poller):
        app = self.parent.app
        socks = dict(poller.poll(0))
        error_msg = []
        while self.socket in socks and socks[self.socket] == zmq.POLLIN:
            sink, data = self.socket.recv_multipart()
            logger.log(TRACE, "peer %s sent %d bytes", self.uuid, len(data))
            with app.download_limiter_lock:
                app.download_limiter.add(len(data))
            self.set_last_reply()
            self.parent.next_request = app.commands.process_reply(
                self.uuid, data)
            if self.parent.next_request is not None:
                logger.log(TRACE, "will reply to peer %s with %d bytes",
                           self.uuid, len(self.parent.next_request))
                with app.medium_priority_output_queue_lock:
                    app.medium_priority_output_queue[self.uuid] \
                        .put(self.parent.next_request)
            else:
                logger.log(TRACE, "no further request to peer %s", self.uuid,)

            self.parent.sleep.set()
            try:
                socks = dict(poller.poll(0))
            except zmq.ZMQError:
                logger.error("Exception while pooling", exc_info=True)
                error_msg.append("got a socket polling error")
                break

        # cleanup block
        if self.socket in socks and socks[self.socket] == zmq.POLLERR:
            error_msg.append("got a socket error")

        if self.timeout is not None:
            if abs(self.timeout - time.time()) > ROLLCALL_TIMEOUT:
                error_msg.append("haven't seen communications")

        self.parent.error_msg = error_msg
        if len(error_msg) > 0:
            self.handle_peer_errors(poller, error_msg)

    def handle_peer_errors(self, poller, error_msg):
        """
        Called when a peer failed to responds to hart-beat or we've seen
        socket errors.

        The corresponding socket is removed from the poller and is closed.
        Associated queues are all discarded and a reconnect is
        scheduled.
        """
        app = self.parent.app
        self.parent.set_status(
            "Stopping client: %s -- %s" % (self.uuid, " and ".join(error_msg)),
            logging.WARNING)

        poller.unregister(self.socket)
        self.socket.close(0)
        self.socket = None
        self.timeout = None

        # Discard everything queued by this peer.
        with app.high_priority_output_queue_lock:
            del app.high_priority_output_queue[self.uuid]
        with app.medium_priority_output_queue_lock:
            del app.medium_priority_output_queue[self.uuid]
        with app.low_priority_output_queue_lock:
            del app.low_priority_output_queue[self.uuid]
        with app.file_request_output_queue_lock:
            del app.file_request_output_queue[self.uuid]

        # Increasing the time until the next reconnect attempt
        # but not larger than CLIENT_RECONNECT_MAX.
        self.reconnect_mod = min(self.reconnect_mod + CLIENT_RECONNECT_MOD,
                                 CLIENT_RECONNECT_MAX)
        # SStore the time when we should attmpt next reconnect.
        next_time = time.time() + self.reconnect_mod
        self.connect_time = next_time
        logger.debug("socket closed for peer %s; "
                     "will attempt reconnect at %r",
                     self.uuid, next_time)
        self.parent.sleep.set()


class TacoClients(TacoThread):
    """
    A thread that manages the communication with peers.


    These are "clients" according to the
    [zmq_curve](http://api.zeromq.org/4-1:zmq-curve) which states that:
    > A socket using CURVE can be either client or server,
    > at any moment, but not both.
    > The role is independent of bind/connect direction.

    To become a CURVE client, the application sets the ZMQ_CURVE_SERVERKEY
    option with the long-term public key of the server it intends to
    connect to, or accept connections from, next. The application then
    sets the ZMQ_CURVE_PUBLICKEY and ZMQ_CURVE_SECRETKEY
    options with its client long-term key pair.

    """
    def __init__(self, app):
        logger.debug('clients manager is being constructed...')
        super(TacoClients, self).__init__(app, name="thTacoClients")

        # The inner loop sleeps on each loop 0.1 seconds. Methods that
        # Expect some data right away can prevent next loop from sleeping
        # by setting this event.
        self.sleep = threading.Event()

        self.next_request = ""

        # A dict with keys being peer uuids and keys being Peer instances.
        self.peers = {}

        # A dict with keys being peer uuids and keys being zmq sockets.
        # self.client_sockets = {}
        #
        # self.next_rollcall = {}
        # self.client_connect_time = {}
        # self.client_reconnect_mod = {}
        #
        # self.client_last_reply_time = {}
        self.client_last_reply_time_lock = threading.Lock()

        # self.client_timeout = {}

        self.connect_block_time = 0

        self.file_request_time = time.time()
        self.max_download_rate = 0.0
        self.max_upload_rate = 0.0
        self.chunk_request_rate = 0.0
        self.error_msg = []

        # We keep an integer in settings that tracks the number of times
        # the settings were saved. Inhere we store the value of that
        # integer last time we inspected the settings and we use
        # settings_changed() whn we see a discrepancy.
        self.settings_trace_number = 1

        self.client_ctx = None
        self.client_auth = None
        self.public_dir = None
        self.private_dir = None
        logger.debug('clients manager constructed')

    def create(self):
        """ Called from run() to initialize the state at thread startup. """
        self.set_status("Client Startup")
        self.set_status("Creating zmq Contexts", logging.INFO)
        self.client_ctx = zmq.Context()

        if not self.app.no_encryption:
            self.set_status("Starting zmq ThreadedAuthenticator", logging.INFO)

            self.client_auth = ThreadAuthenticator(
                self.client_ctx, log=logging.getLogger('tacozmq.c_auth'))
            self.client_auth.start()
            self.client_auth.thread.name = "thTacoClientAuth"

            with self.app.settings_lock:
                self.public_dir = self.app.public_dir
                self.private_dir = self.app.private_dir

            self.set_status("configuring Curve to use public key dir: %s" %
                            self.public_dir)
            self.client_auth.configure_curve(
                domain='*', location=self.public_dir)

        logger.debug("clients manager started")

    def terminate(self):
        self.set_status("Terminating Clients")
        for peer in self.peers.values():
            peer.socket.close(0)
            peer.socket = None

        self.set_status("Stopping zmq ThreadedAuthenticator")
        if self.client_auth is not None:
            self.client_auth.stop()
            self.client_auth = None
        self.client_ctx.term()
        self.client_ctx = None
        self.set_status("Clients Exit")

    def run(self):
        self.create()

        poller = zmq.Poller()
        while not self.stop.is_set():
            # Do some soul searching.
            self.sleep.wait(0.1)
            self.sleep.clear()

            # Were we asked to leave?
            if self.stop.is_set():
                break

            time_now = time.time()
            logger.log(TRACE, 'client loop at t %r and previous at %r',
                       time_now, self.connect_block_time)

            # Every second or so we update the state of peers.
            if abs(time_now - self.connect_block_time) > 1:
                self.state_update(self.client_ctx, poller)
                self.connect_block_time = time.time()

            # Anything to do?
            if not len(self.peers):
                continue

            # We have some peers connected so shuffle them and let's roll.
            peer_keys = list(self.peers.keys())
            random.shuffle(peer_keys)
            for peer_uuid in peer_keys:
                self.peers[peer_uuid].perform(poller)

            logger.log(TRACE, 'client loop done')

        self.terminate()

    def settings_changed(self):
        """ Called when we detect a change in settings. """
        self.settings_trace_number = self.app.store.trace_number

        if not self.app.no_encryption:
            with self.app.settings_lock:
                self.public_dir = self.app.public_dir
            self.set_status("Configuring Curve to use public key dir: %s" %
                            self.public_dir)
            # Certificates can be added and removed in directory at any time.
            # configure_curve must be called every time certificates are added
            # or removed, in order to update the Authenticator’s state.
            self.client_auth.configure_curve(
                domain='*', location=self.public_dir)

    def get_client_last_reply(self, peer_uuid):
        """ Gets the last time a client was responsive or -1 if never seen. """
        with self.client_last_reply_time_lock:
            try:
                return self.peers[peer_uuid].last_reply_time
            except KeyError:
                return -1

    def is_client_responsive(self, peer_uuid):
        """ Tell if we've seen data from a peer in a resonable time. """

        last_reply = self.get_client_last_reply(peer_uuid)
        # Is this peer responsive?
        # If the timeout has not yet expired it is responsive.
        return abs(last_reply - time.time()) < ROLLCALL_TIMEOUT

    def responsive_peer_ids(self):
        """ Get a list of responsive peers. """
        return [
            peer_uuid for peer_uuid in self.app.settings["Peers"]
            if self.is_client_responsive(peer_uuid)]

    def run_peer(self, peer_uuid, client_ctx, poller):
        """ Executed as part of the state update for each enabled peer. """
        peer_data = self.app.settings["Peers"][peer_uuid]
        if peer_uuid in self.peers:
            peer = self.peers[peer_uuid]
        else:
            peer = Peer(self, peer_uuid)
            self.peers[peer_uuid] = peer

        # If we haven't seen this peer before we initialize the wait time
        # until next reconnect attempt to be the minimum one.
        # if peer_uuid not in self.client_reconnect_mod:
        #     self.client_reconnect_mod[peer_uuid] = CLIENT_RECONNECT_MIN

        # If we haven't computed a time when this client should connect we
        # do that now based on current time and stored delta.
        # if peer_uuid not in self.client_connect_time:
        #     self.client_connect_time[peer_uuid] = \
        #         time.time() + self.client_reconnect_mod[peer_uuid]

        # Is it time to contact this peer?
        if time.time() < peer.connect_time:
            return

        # Is it already started?
        if peer.socket is not None:
            return

        self.set_status("Starting Client for: %s" % peer_uuid)
        try:
            ip_of_client = gethostbyname(peer_data["hostname"])
        except gaierror:
            self.set_status("Starting of client failed due to bad "
                            "dns lookup: %s" % peer_uuid)
            return

        new_socket = peer.create_peer_socket(
            client_ctx, peer_data, ip_of_client)
        poller.register(new_socket, zmq.POLLIN)

    def state_update(self, client_ctx, poller):
        """ Called regularly to update the status of the peers. """
        logger.log(TRACE, 'state being updated...')

        # Check if settings changed and update accordingly.
        # We use this mechanism because, if keys are added / removed,
        # the ThreadAuthenticator would not notice
        # (configure_curve needs to be called again).
        if self.settings_trace_number != self.app.store.trace_number:
            self.settings_changed()

        with self.app.settings_lock:
            self.max_upload_rate = \
                self.app.settings["Upload Limit"] * KB
            self.max_download_rate = \
                self.app.settings["Download Limit"] * KB

        self.chunk_request_rate = \
            float(FILESYSTEM_CHUNK_SIZE) / float(self.max_download_rate)

        with self.app.settings_lock:
            for peer_uuid in self.app.settings["Peers"].keys():
                if self.app.settings["Peers"][peer_uuid]["enabled"]:
                    self.run_peer(peer_uuid, client_ctx, poller)
        logger.log(TRACE, 'state updated')
