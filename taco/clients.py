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
from taco.constants import *
import os
from socket import gethostbyname, gaierror
import sys
import random

from taco.utils import norm_join

if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue


class TacoClients(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.app = app

        # Set this to terminate the thread.
        self.stop = threading.Event()
        self.sleep = threading.Event()

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1
        self.next_request = ""

        self.clients = {}

        self.next_rollcall = {}
        self.client_connect_time = {}
        self.client_reconnect_mod = {}

        self.client_last_reply_time = {}
        self.client_last_reply_time_lock = threading.Lock()

        self.client_timeout = {}

        self.connect_block_time = 0

        self.file_request_time = time.time()
        self.max_download_rate = 0.0
        self.max_upload_rate = 0.0
        self.chunk_request_rate = 0.0
        self.error_msg = []

    def set_client_last_reply(self, peer_uuid):
        # logging.debug("Got Reply from: " + peer_uuid)
        self.client_reconnect_mod[peer_uuid] = CLIENT_RECONNECT_MIN
        self.client_timeout[peer_uuid] = time.time() + ROLLCALL_TIMEOUT
        with self.client_last_reply_time_lock:
            self.client_last_reply_time[peer_uuid] = time.time()

    def get_client_last_reply(self, peer_uuid):
        with self.client_last_reply_time_lock:
            if peer_uuid in self.client_last_reply_time:
                return self.client_last_reply_time[peer_uuid]
        return -1

    def set_status(self, text, level=0):
        if level == 1:
            logging.info(text)
        elif level == 0:
            logging.debug(text)
        elif level == 2:
            logging.warning(text)
        elif level == 3:
            logging.error(text)
        with self.status_lock:
            self.status = text
            self.status_time = time.time()

    def get_status(self):
        with self.status_lock:
            return self.status, self.status_time

    def create_peer_socket(self, peer_uuid, client_ctx,
                           private_dir, peer_data, ip_of_client):
        """ Creates the socket, sets it up, creates queues for it and
        saves a reference in our list of clients. """
        new_socket = client_ctx.socket(zmq.DEALER)
        new_socket.setsockopt(zmq.LINGER, 0)
        client_public, client_secret = zmq.auth.load_certificate(
            norm_join(private_dir,
                      KEY_GENERATION_PREFIX + "-client.key_secret"))
        new_socket.curve_secretkey = client_secret
        new_socket.curve_publickey = client_public
        new_socket.curve_serverkey = str(peer_data["serverkey"])
        address_str = "tcp://%s:%d" % (ip_of_client, peer_data["port"])
        new_socket.connect(address_str)
        self.set_status("Client for %s started at %s" % (
            peer_uuid, address_str))
        self.next_rollcall[peer_uuid] = time.time()

        with self.app.high_priority_output_queue_lock:
            self.app.high_priority_output_queue[peer_uuid] = Queue()
        with self.app.medium_priority_output_queue_lock:
            self.app.medium_priority_output_queue[peer_uuid] = Queue()
        with self.app.low_priority_output_queue_lock:
            self.app.low_priority_output_queue[peer_uuid] = Queue()
        with self.app.file_request_output_queue_lock:
            self.app.file_request_output_queue[peer_uuid] = Queue()

        self.clients[peer_uuid] = new_socket
        return new_socket

    def run_peer(self, peer_uuid, client_ctx, private_dir, poller):
        """ Executed as part of the state update for each enabled peer. """
        peer_data = self.app.settings["Peers"][peer_uuid]

        # If we haven't seen this peer before we initialize the wait time
        # until next reconnect attempt to be the minimum one.
        if peer_uuid not in self.client_reconnect_mod:
            self.client_reconnect_mod[peer_uuid] = CLIENT_RECONNECT_MIN

        # If we haven't computed a time when this client should connect we
        # do that now based on current time and stored delta.
        if peer_uuid not in self.client_connect_time:
            self.client_connect_time[peer_uuid] = \
                time.time() + self.client_reconnect_mod[peer_uuid]

        # If a timeout limit was not yet computed then compute one now.
        if peer_uuid not in self.client_timeout:
            self.client_timeout[peer_uuid] = time.time() + ROLLCALL_TIMEOUT

        # Is it time to contact this peer?
        if time.time() < self.client_connect_time[peer_uuid]:
            return

        # Is it already started?
        if peer_uuid in self.clients.keys():
            return

        self.set_status("Starting Client for: %s" % peer_uuid)
        try:
            ip_of_client = gethostbyname(peer_data["hostname"])
        except gaierror:
            self.set_status("Starting of client failed due to bad "
                            "dns lookup: %s" % peer_uuid)
            return

        new_socket = self.create_peer_socket(
            peer_uuid, client_ctx, private_dir, peer_data, ip_of_client)
        poller.register(new_socket, zmq.POLLIN)

    def state_update(self, client_ctx, private_dir, poller):
        """ Called regularly to update the status of the peers. """
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
                    self.run_peer(peer_uuid, client_ctx, private_dir, poller)

    def perform_peer(self, peer_uuid, poller):
        """ Called for connected peers to do some work. """
        peer_socket = self.clients[peer_uuid]
        self.perform_high_priority(peer_uuid, peer_socket)
        self.perform_medium_priority(peer_uuid, peer_socket)
        self.perform_file_transaction(peer_uuid, peer_socket)
        self.perform_low_priority(peer_uuid, peer_socket)
        self.perform_rollcall(peer_uuid, peer_socket)
        self.receive_block(peer_uuid, peer_socket, poller)

    def run(self):
        self.set_status("Client Startup")
        self.set_status("Creating zmq Contexts", 1)
        client_ctx = zmq.Context()
        self.set_status("Starting zmq ThreadedAuthenticator", 1)
        # client_auth = zmq.auth.ThreadedAuthenticator(client_ctx)
        client_auth = ThreadAuthenticator(client_ctx)
        client_auth.start()

        with self.app.settings_lock:
            public_dir = norm_join(
                self.app.settings["TacoNET Certificates Store"],
                self.app.settings["Local UUID"],
                "public")
            private_dir = norm_join(
                self.app.settings["TacoNET Certificates Store"],
                self.app.settings["Local UUID"],
                "private")

        self.set_status("Configuring Curve to use publickey dir:" + public_dir)
        client_auth.configure_curve(domain='*', location=public_dir)

        poller = zmq.Poller()
        while not self.stop.is_set():
            # Do some soul searching.
            self.sleep.wait(0.1)
            self.sleep.clear()

            # Were we asked to leave?
            if self.stop.is_set():
                break

            # Every second or so we update the state of peers.
            if abs(time.time() - self.connect_block_time) > 1:
                self.state_update(client_ctx, private_dir, poller)
                self.connect_block_time = time.time()

            # Anything to do?
            if len(self.clients.keys()) == 0:
                continue

            # We have some peers connected so shuffle them and let's roll.
            peer_keys = self.clients.keys()
            random.shuffle(peer_keys)
            for peer_uuid in peer_keys:
                self.perform_peer(peer_uuid, poller)

        self.set_status("Terminating Clients")
        for peer_uuid in self.clients.keys():
            self.clients[peer_uuid].close(0)

        self.set_status("Stopping zmq ThreadedAuthenticator")
        client_auth.stop()
        client_ctx.term()
        self.set_status("Clients Exit")

    def perform_high_priority(self, peer_uuid, peer_socket):
        """ High priority queue processing. """
        with self.app.high_priority_output_queue_lock:
            while not self.app.high_priority_output_queue[peer_uuid].empty():
                self.set_status("high priority output q not empty:" + peer_uuid)
                data = self.app.high_priority_output_queue[peer_uuid].get()
                peer_socket.send_multipart(['', data])
                self.sleep.set()
                with self.app.upload_limiter_lock:
                    self.app.upload_limiter.add(len(data))

    def perform_medium_priority(self, peer_uuid, peer_socket):
        """ Medium priority queue processing. """
        with self.app.medium_priority_output_queue_lock:
            while not self.app.medium_priority_output_queue[peer_uuid].empty():
                self.set_status("medium priority output q not empty:" + peer_uuid)
                data = self.app.medium_priority_output_queue[peer_uuid].get()
                peer_socket.send_multipart(['', data])
                self.sleep.set()
                with self.app.upload_limiter_lock:
                    self.app.upload_limiter.add(len(data))

    def perform_low_priority(self, peer_uuid, peer_socket):
        """ Low priority queue processing. """
        with self.app.low_priority_output_queue_lock:
            if not self.app.low_priority_output_queue[peer_uuid].empty():
                with self.app.upload_limiter_lock:
                    upload_rate = self.app.upload_limiter.get_rate()
                if upload_rate < self.max_upload_rate:
                    self.set_status(
                        "low priority output q not empty+free bw:" + peer_uuid)
                    data = self.app.low_priority_output_queue[peer_uuid].get()
                    peer_socket.send_multipart(['', data])
                    self.sleep.set()
                    with self.app.upload_limiter_lock:
                        self.app.upload_limiter.add(len(data))

    def perform_file_transaction(self, peer_uuid, peer_socket):
        """ File request queue, aka the download throttle. """
        if time.time() < self.file_request_time:
            return

        self.file_request_time = time.time()
        with self.app.file_request_output_queue_lock:
            if not self.app.file_request_output_queue[peer_uuid].empty():
                with self.app.download_limiter_lock:
                    download_rate = self.app.download_limiter.get_rate()

                bw_percent = download_rate / self.max_download_rate
                wait_time = self.chunk_request_rate * bw_percent

                # self.set_status(str((download_rate,
                #   self.max_download_rate,self.chunk_request_rate,
                #   bw_percent,wait_time)))
                if wait_time > 0.01:
                    self.file_request_time += wait_time

                if download_rate < self.max_download_rate:
                    self.set_status(
                        "filereq output q not empty+free bw:" + peer_uuid)
                    data = self.app.file_request_output_queue[peer_uuid].get()
                    peer_socket.send_multipart(['', data])
                    self.sleep.set()
                    with self.app.upload_limiter_lock:
                        self.app.upload_limiter.add(len(data))

    def perform_rollcall(self, peer_uuid, peer_socket):
        """ File request queue, aka the download throttle. """
        if self.next_rollcall[peer_uuid] >= time.time():
            return
        data = self.app.commands.Request_Rollcall()
        peer_socket.send_multipart(['', data])
        with self.app.upload_limiter_lock:
            self.app.upload_limiter.add(len(data))
        self.next_rollcall[peer_uuid] = \
            time.time() + random.randint(ROLLCALL_MIN, ROLLCALL_MAX)
        self.sleep.set()

    def receive_block(self, peer_uuid, peer_socket, poller):
        # RECEIVE BLOCK
        socks = dict(poller.poll(0))
        while peer_socket in socks and socks[peer_socket] == zmq.POLLIN:
            sink, data = peer_socket.recv_multipart()
            with self.app.download_limiter_lock:
                self.app.download_limiter.add(len(data))
            self.set_client_last_reply(peer_uuid)
            self.next_request = self.app.commands.Process_Reply(peer_uuid, data)
            if self.next_request != "":
                with self.app.medium_priority_output_queue_lock:
                    self.app.medium_priority_output_queue[peer_uuid] \
                        .put(self.next_request)
            self.sleep.set()
            socks = dict(poller.poll(0))

        # cleanup block
        self.error_msg = []
        if peer_socket in socks and socks[peer_socket] == zmq.POLLERR:
            self.error_msg.append("got a socket error")

        if abs(self.client_timeout[peer_uuid] - time.time()) > ROLLCALL_TIMEOUT:
            self.error_msg.append("haven't seen communications")

        if len(self.error_msg) > 0:
            self.handle_peer_errors(
                peer_uuid, peer_socket, poller, self.error_msg)

    def handle_peer_errors(self, peer_uuid, peer_socket, poller, error_msg):
        """
        Called when a peer failed to responds to hartbeat or we've seen
        socket errors.

        The corresponding socket is removed from the pooler and is closed.
        Associated queues are all discarded and a reconnect is
        scheduled.
        """
        self.set_status(
            "Stopping client: %s -- %s" % (
                peer_uuid, " and ".join(error_msg)),
            2)

        poller.unregister(peer_socket)
        peer_socket.close(0)
        del self.clients[peer_uuid]
        del self.client_timeout[peer_uuid]

        # Discard everything queued by this peer.
        with self.app.high_priority_output_queue_lock:
            del self.app.high_priority_output_queue[peer_uuid]
        with self.app.medium_priority_output_queue_lock:
            del self.app.medium_priority_output_queue[peer_uuid]
        with self.app.low_priority_output_queue_lock:
            del self.app.low_priority_output_queue[peer_uuid]
        with self.app.file_request_output_queue_lock:
            del self.app.file_request_output_queue[peer_uuid]

        # Increasing the time until the next reconnect attempt
        # but not larger than CLIENT_RECONNECT_MAX.
        self.client_reconnect_mod[peer_uuid] = \
            min(self.client_reconnect_mod[peer_uuid] + CLIENT_RECONNECT_MOD,
                CLIENT_RECONNECT_MAX)
        # SStore the time when we should attmpt next reconnect.
        self.client_connect_time[peer_uuid] = \
            time.time() + self.client_reconnect_mod[peer_uuid]
