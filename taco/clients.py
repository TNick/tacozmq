import threading
import logging
import time
import zmq
from zmq.auth.thread import ThreadAuthenticator
import taco.globals
from taco.constants import *
import taco.commands
import os
import socket
import sys
import random

if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue


class TacoClients(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

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

    def run_peer(self, peer_uuid, client_ctx, private_dir, poller):
        peer_data = taco.globals.settings["Peers"][peer_uuid]
        # init some defaults
        if peer_uuid not in self.client_reconnect_mod:
            self.client_reconnect_mod[
                peer_uuid] = CLIENT_RECONNECT_MIN
        if peer_uuid not in self.client_connect_time:
            self.client_connect_time[
                peer_uuid] = time.time() + self.client_reconnect_mod[peer_uuid]
        if peer_uuid not in self.client_timeout:
            self.client_timeout[
                peer_uuid] = time.time() + ROLLCALL_TIMEOUT

        if time.time() >= self.client_connect_time[peer_uuid]:
            if peer_uuid not in self.clients.keys():
                self.set_status("Starting Client for: " + peer_uuid)
                try:
                    ip_of_client = socket.gethostbyname(peer_data["hostname"])
                except Exception:
                    self.set_status("Starting of client failed due to bad "
                                    "dns lookup: %s" % peer_uuid)
                    return
                self.clients[peer_uuid] = client_ctx.socket(zmq.DEALER)
                self.clients[peer_uuid].setsockopt(zmq.LINGER, 0)
                client_public, client_secret = zmq.auth.load_certificate(
                    os.path.normpath(
                        os.path.abspath(
                            os.path.join(
                                private_dir,
                                KEY_GENERATION_PREFIX + "-client.key_secret"))))
                self.clients[peer_uuid].curve_secretkey = client_secret
                self.clients[peer_uuid].curve_publickey = client_public
                self.clients[peer_uuid].curve_serverkey = str(
                    peer_data["serverkey"])
                self.clients[peer_uuid].connect("tcp://" + ip_of_client + ":" + str(
                    peer_data["port"]))
                self.next_rollcall[peer_uuid] = time.time()

                with taco.globals.high_priority_output_queue_lock:
                    taco.globals.high_priority_output_queue[peer_uuid] = Queue()
                with taco.globals.medium_priority_output_queue_lock:
                    taco.globals.medium_priority_output_queue[peer_uuid] = Queue()
                with taco.globals.low_priority_output_queue_lock:
                    taco.globals.low_priority_output_queue[peer_uuid] = Queue()
                with taco.globals.file_request_output_queue_lock:
                    taco.globals.file_request_output_queue[peer_uuid] = Queue()

                poller.register(self.clients[peer_uuid], zmq.POLLIN)

    def run(self):
        self.set_status("Client Startup")
        self.set_status("Creating zmq Contexts", 1)
        client_ctx = zmq.Context()
        self.set_status("Starting zmq ThreadedAuthenticator", 1)
        # client_auth = zmq.auth.ThreadedAuthenticator(client_ctx)
        client_auth = ThreadAuthenticator(client_ctx)
        client_auth.start()

        with taco.globals.settings_lock:
            public_dir = os.path.normpath(os.path.abspath(os.path.join(
                taco.globals.settings["TacoNET Certificates Store"],
                taco.globals.settings["Local UUID"],
                "public")))
            private_dir = os.path.normpath(os.path.abspath(os.path.join(
                taco.globals.settings["TacoNET Certificates Store"],
                taco.globals.settings["Local UUID"],
                "private")))

        self.set_status("Configuring Curve to use publickey dir:" + public_dir)
        client_auth.configure_curve(domain='*', location=public_dir)

        poller = zmq.Poller()
        while not self.stop.is_set():
            # logging.debug("PRE")
            result = self.sleep.wait(0.1)
            # logging.debug(result)
            self.sleep.clear()
            if self.stop.is_set():
                break

            if abs(time.time() - self.connect_block_time) > 1:
                with taco.globals.settings_lock:
                    self.max_upload_rate = \
                        taco.globals.settings["Upload Limit"] * KB
                    self.max_download_rate = \
                        taco.globals.settings["Download Limit"] * KB
                self.chunk_request_rate = \
                    float(FILESYSTEM_CHUNK_SIZE) / float(self.max_download_rate)

                # logging.debug(str((self.max_download_rate,FILESYSTEM_CHUNK_SIZE,
                # self.chunk_request_rate)))
                self.connect_block_time = time.time()
                with taco.globals.settings_lock:
                    for peer_uuid in taco.globals.settings["Peers"].keys():
                        if taco.globals.settings["Peers"][peer_uuid]["enabled"]:
                            self.run_peer(
                                peer_uuid, client_ctx, private_dir, poller)

            if len(self.clients.keys()) == 0:
                continue

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

    def perform_peer(self, peer_uuid, poller):
        # self.set_status("Socket Write Possible:" + peer_uuid)
        peer_data = self.clients[peer_uuid]

        # high priority queue processing
        with taco.globals.high_priority_output_queue_lock:
            while not taco.globals.high_priority_output_queue[peer_uuid].empty():
                self.set_status("high priority output q not empty:" + peer_uuid)
                data = taco.globals.high_priority_output_queue[peer_uuid].get()
                peer_data.send_multipart(['', data])
                self.sleep.set()
                with taco.globals.upload_limiter_lock:
                    taco.globals.upload_limiter.add(len(data))

        # medium priority queue processing
        with taco.globals.medium_priority_output_queue_lock:
            while not taco.globals.medium_priority_output_queue[peer_uuid].empty():
                self.set_status("medium priority output q not empty:" + peer_uuid)
                data = taco.globals.medium_priority_output_queue[peer_uuid].get()
                peer_data.send_multipart(['', data])
                self.sleep.set()
                with taco.globals.upload_limiter_lock:
                    taco.globals.upload_limiter.add(len(data))

        # filereq q, aka the download throttle
        if time.time() >= self.file_request_time:
            self.file_request_time = time.time()
            with taco.globals.file_request_output_queue_lock:
                if not taco.globals.file_request_output_queue[peer_uuid].empty():
                    with taco.globals.download_limiter_lock:
                        download_rate = taco.globals.download_limiter.get_rate()

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
                        data = taco.globals.file_request_output_queue[peer_uuid].get()
                        peer_data.send_multipart(['', data])
                        self.sleep.set()
                        with taco.globals.upload_limiter_lock:
                            taco.globals.upload_limiter.add(len(data))

        # low priority queue processing
        with taco.globals.low_priority_output_queue_lock:
            if not taco.globals.low_priority_output_queue[peer_uuid].empty():
                with taco.globals.upload_limiter_lock:
                    upload_rate = taco.globals.upload_limiter.get_rate()
                if upload_rate < self.max_upload_rate:
                    self.set_status(
                        "low priority output q not empty+free bw:" + peer_uuid)
                    data = taco.globals.low_priority_output_queue[peer_uuid].get()
                    peer_data.send_multipart(['', data])
                    self.sleep.set()
                    with taco.globals.upload_limiter_lock:
                        taco.globals.upload_limiter.add(len(data))

        # rollcall special case
        if self.next_rollcall[peer_uuid] < time.time():
            # self.set_status("Requesting Rollcall from: " + peer_uuid)
            data = taco.commands.Request_Rollcall()
            peer_data.send_multipart(['', data])
            with taco.globals.upload_limiter_lock:
                taco.globals.upload_limiter.add(len(data))
            self.next_rollcall[peer_uuid] = \
                time.time() + random.randint(ROLLCALL_MIN,
                                             ROLLCALL_MAX)
            self.sleep.set()
            # continue

        # RECEIVE BLOCK
        socks = dict(poller.poll(0))
        while peer_data in socks and socks[peer_data] == zmq.POLLIN:
            # self.set_status("Socket Read Possible")
            sink, data = peer_data.recv_multipart()
            with taco.globals.download_limiter_lock:
                taco.globals.download_limiter.add(len(data))
            self.set_client_last_reply(peer_uuid)
            self.next_request = taco.commands.Process_Reply(peer_uuid, data)
            if self.next_request != "":
                with taco.globals.medium_priority_output_queue_lock:
                    taco.globals.medium_priority_output_queue[peer_uuid] \
                        .put(self.next_request)
            self.sleep.set()
            socks = dict(poller.poll(0))

        # cleanup block
        self.error_msg = []
        if peer_data in socks and socks[
            peer_data] == zmq.POLLERR:
            self.error_msg.append("got a socket error")
        if abs(self.client_timeout[
                   peer_uuid] - time.time()) > ROLLCALL_TIMEOUT:
            self.error_msg.append(
                "haven't seen communications")

        if len(self.error_msg) > 0:
            self.set_status("Stopping client: " + peer_uuid + " -- " +
                            " and ".join(self.error_msg), 2)
            poller.unregister(peer_data)
            peer_data.close(0)
            del self.clients[peer_uuid]
            del self.client_timeout[peer_uuid]

            with taco.globals.high_priority_output_queue_lock:
                del taco.globals.high_priority_output_queue[peer_uuid]
            with taco.globals.medium_priority_output_queue_lock:
                del taco.globals.medium_priority_output_queue[peer_uuid]
            with taco.globals.low_priority_output_queue_lock:
                del taco.globals.low_priority_output_queue[peer_uuid]
            with taco.globals.file_request_output_queue_lock:
                del taco.globals.file_request_output_queue[peer_uuid]

            self.client_reconnect_mod[peer_uuid] = min(
                self.client_reconnect_mod[peer_uuid] + CLIENT_RECONNECT_MOD,
                CLIENT_RECONNECT_MAX)
            self.client_connect_time[peer_uuid] = \
                time.time() + self.client_reconnect_mod[peer_uuid]
