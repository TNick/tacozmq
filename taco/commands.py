# -*- coding: utf-8 -*-
"""
Commands used by the api.
"""
from __future__ import unicode_literals
from __future__ import print_function

from umsgpack import packb, unpackb
import logging
import sys
import time
import uuid

from .constants import *

logger = logging.getLogger('tacozmq.cmd')
if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue


class TacoCommands(object):
    def __init__(self, app):
        super(TacoCommands, self).__init__()
        self.app = app

    def create_request(self, command=NET_GARBAGE, data=None):
        with self.app.settings_lock:
            local_uuid = self.app.settings["Local UUID"]
        request = {
            NET_IDENT: local_uuid,
            NET_REQUEST: command,
            NET_DATABLOCK: '' if data is None else data
        }
        logger.log(TRACE, 'request command %r, data %r', command, data)
        return request

    def create_reply(self, command=NET_GARBAGE, data=None):
        with self.app.settings_lock:
            local_uuid = self.app.settings["Local UUID"]
        reply = {
            NET_IDENT: local_uuid,
            NET_REPLY: command,
            NET_DATABLOCK: '' if data is None else data
        }
        logger.log(TRACE, 'reply command %r, data %r', command, data)
        return reply

    def process_request(self, packed):
        reply = self.create_request()
        try:
            unpacked = unpackb(packed)
            assert NET_DATABLOCK in unpacked
            assert NET_IDENT in unpacked
        except AssertionError:
            logger.warning("bad request")
            return NO_IDENTITY, packb(reply)

        identity = unpacked[NET_IDENT]
        trunk = unpacked[NET_DATABLOCK]

        if NET_REQUEST in unpacked:
            req_code = unpacked[NET_REQUEST]

            if req_code == NET_REQUEST_GIVE_FILE_CHUNK:
                if "data" in trunk:
                    logger.log(
                        TRACE, "%r NET_REQUEST (FileChunk DATA): %d bytes",
                        identity, len(trunk["data"]))
                else:
                    logger.error(
                        "%r NET_REQUEST (FileChunk DATA): without data",
                        identity)
            else:
                logger.log(TRACE, "%r NET_REQUEST: %r", identity, unpacked)

            if req_code == NET_REQUEST_ROLLCALL:
                return identity, self.reply_rollcall_cmd()

            if req_code == NET_REQUEST_CERTS:
                return identity, self.reply_certs_cmd(identity, trunk)

            if req_code == NET_REQUEST_CHAT:
                return identity, self.reply_chat_cmd(identity, trunk)

            if req_code == NET_REQUEST_SHARE_LISTING:
                return identity, self.reply_share_listing_cmd(identity, trunk)

            if req_code == NET_REQUEST_SHARE_LISTING_RESULTS:
                return identity, self.reply_share_listing_result_cmd(
                    identity, trunk)

            if req_code == NET_REQUEST_GET_FILE_CHUNK:
                return identity, self.reply_get_file_chunk_cmd(identity, trunk)

            if req_code == NET_REQUEST_GIVE_FILE_CHUNK:
                return identity, self.reply_give_file_chunk_cmd(identity, trunk)

            logger.warning("%r used unknown NET_REQUEST code %r: %r",
                           identity, req_code, unpacked)
        else:
            logger.warning("%r made unknown request (no NET_REQUEST): %r",
                           identity, unpacked)

        return NO_IDENTITY, packb(reply)

    def process_reply(self, peer_uuid, packed):
        response = ""
        try:
            unpacked = unpackb(packed)
            assert NET_DATABLOCK in unpacked
            assert NET_IDENT in unpacked
        except AssertionError:
            logger.warning("bad reply from %r", peer_uuid)
            return response

        trunk = unpacked[NET_DATABLOCK]

        if NET_REPLY in unpacked:
            reply_id = unpacked[NET_REPLY]
            logger.log(TRACE, "%r NET_REPLY %r: %r",
                       peer_uuid, reply_id, unpacked)

            if reply_id == NET_REPLY_ROLLCALL:
                return self.process_reply_rollcall(peer_uuid, trunk)

            if reply_id == NET_REPLY_CERTS:
                return self.process_reply_certs(peer_uuid, trunk)

            if reply_id == NET_REPLY_GET_FILE_CHUNK:
                return self.process_reply_get_file_chunk(peer_uuid, trunk)

            logger.warning("unknown reply id %r in data: %r",
                           reply_id, unpacked)
        else:
            logger.warning("%r gave unknown reply (no NET_REPLY): %r",
                           unpacked[NET_IDENT], unpacked)
        return response

    def request_chat_cmd(self, chat_msg):
        output_block = self.create_request(
            NET_REQUEST_CHAT, [time.time(), chat_msg])
        with self.app.chat_log_lock:
            self.app.chat_log.append(
                [self.app.settings["Local UUID"], time.time(), chat_msg])
            with self.app.chat_uuid_lock:
                self.app.chat_uuid = uuid.uuid4().hex
            if len(self.app.chat_log) > CHAT_LOG_MAXSIZE:
                self.app.chat_log = self.app.chat_log[
                                    len(self.app.chat_log)-CHAT_LOG_MAXSIZE:]
                logger.log(TRACE, "chat trimmed to %d elements",
                           len(self.app.chat_log))

        self.app.Add_To_All_Output_Queues(packb(output_block))
        logger.log(TRACE, "chat sent to all peers (%d bytes): %r",
                   len(output_block), chat_msg)

    def reply_chat_cmd(self, peer_uuid, data_block):
        logger.log(TRACE, "chat received from %r: %r", peer_uuid, data_block)
        with self.app.chat_log_lock:
            self.app.chat_log.append([peer_uuid] + data_block)
            with self.app.chat_uuid_lock:
                self.app.chat_uuid = uuid.uuid4().hex
            if len(self.app.chat_log) > CHAT_LOG_MAXSIZE:
                self.app.chat_log = self.app.chat_log[
                                    len(self.app.chat_log)-CHAT_LOG_MAXSIZE:]
                logger.log(TRACE, "chat trimmed to %d elements",
                           len(self.app.chat_log))
        reply = self.create_reply(NET_REPLY_CHAT, {})
        return packb(reply)

    def request_rollcall_cmd(self):
        request = self.create_request(NET_REQUEST_ROLLCALL, "")
        logger.log(TRACE, "requesting roll call")
        return packb(request)

    def reply_rollcall_cmd(self):
        logger.log(TRACE, "replying to rollcall...")
        peers_i_can_talk_to = []
        with self.app.settings_lock:
            for peer_uuid in self.app.settings["Peers"].keys():
                last_reply = self.app.clients.get_client_last_reply(peer_uuid)
                # Is this peer responsive?
                if abs(last_reply - time.time()) < ROLLCALL_TIMEOUT:
                    # The timeout has not yet expired.
                    peers_i_can_talk_to.append(peer_uuid)
        reply = self.create_reply(
            NET_REPLY_ROLLCALL,
            [self.app.settings["Nickname"], self.app.settings["Local UUID"]] +
            peers_i_can_talk_to)
        logger.log(TRACE, "rollcall reply sent to %d peers (%d bytes)",
                   len(peers_i_can_talk_to), len(reply))
        return packb(reply)

    def process_reply_rollcall(self, peer_uuid, unpacked):
        requested_peers = []
        with self.app.settings_lock:
            new_nickname = unpacked[0]
            if peer_uuid in self.app.settings["Peers"]:
                peer_data = self.app.settings["Peers"][peer_uuid]
                if "nickname" in peer_data:
                    if peer_data["nickname"] != new_nickname:
                        if NICKNAME_CHECKER.match(new_nickname):
                            peer_data["nickname"] = new_nickname
                            self.app.store.save(False)
                            logger.log(TRACE, "peer %s nickname updated to %s",
                                       peer_uuid, new_nickname)
                        else:
                            logger.log(TRACE, "peer %s does not match %s",
                                       peer_uuid, NICKNAME_CHECKER)
                else:
                    if NICKNAME_CHECKER.match(new_nickname):
                        peer_data["nickname"] = new_nickname
                    else:
                        peer_data["nickname"] = "GENERIC NICKNAME"
                    self.app.store.save(False)
            else:
                logger.log(TRACE, "peer %s not in list", peer_uuid)

            for peer_id in unpacked[1:]:
                if UUID_CHECKER.match(peer_id):
                    if peer_id not in self.app.settings["Peers"].keys() \
                            and peer_id != self.app.settings["Local UUID"]:
                        requested_peers.append(peer_id)
        logger.log(TRACE, "%d requested peers", len(requested_peers))
        if len(requested_peers) > 0:
            return self.request_certs_cmd(requested_peers)
        return ""

    def request_certs_cmd(self, peer_uuids):
        request = self.create_request(NET_REQUEST_CERTS, peer_uuids)
        logger.log(TRACE, "requesting certificates call")
        return packb(request)

    def reply_certs_cmd(self, peer_uuid, data_block):
        reply = self.create_reply(NET_REPLY_CERTS, {})
        with self.app.settings_lock:
            for peer_uuid in data_block:
                if peer_uuid in self.app.settings["Peers"]:
                    peer_data = self.app.settings["Peers"][peer_uuid]
                    reply[NET_DATABLOCK][peer_uuid] = [
                        peer_data["nickname"],
                        peer_data["hostname"],
                        peer_data["port"],
                        peer_data["clientkey"],
                        peer_data["serverkey"],
                        peer_data["dynamic"]
                    ]
        return packb(reply)

    def process_reply_certs(self, peer_uuid, unpacked):
        response = ""
        logger.debug("Got some new peers to add:" + str(unpacked))
        if not isinstance(unpacked, dict):
            logger.error("expected payload to be dict: %r", unpacked)
            return response

        for peer_id in unpacked.keys():
            if len(unpacked[peer_id]) != 6:
                logger.error("payload for peer %s should have 6 members: %r",
                             peer_id, unpacked)
                continue

            (nickname, hostname, port, clientkey, serverkey, dynamic) = \
                unpacked[peer_id]
            logger.log(TRACE, "peer_id=%r, nickname=%r, hostname=%r, port=%r, "
                              "clientkey=%r, serverkey=%r, dynamic=%r",
                       peer_id, nickname, hostname, port, clientkey,
                       serverkey, dynamic)
            with self.app.settings_lock:
                if peer_id not in self.app.settings["Peers"]:
                    self.app.settings["Peers"][peer_id] = {
                        "hostname": hostname,
                        "port": int(port),
                        "clientkey": clientkey,
                        "serverkey": serverkey,
                        "dynamic": int(dynamic),
                        "enabled": 0,
                        "localnick": "",
                        "nickname": nickname
                    }
                    self.app.store.save(False)
                else:
                    # TODO: shouldn't we try to check/update some values?
                    logger.log(TRACE, "peer %r exists: %r",
                               peer_id, self.app.settings["Peers"][peer_id])
        return response

    def request_share_listing_cmd(
            self, peer_uuid, sharedir, share_listing_uuid):

        with self.app.share_listings_i_care_about_lock:
            self.app.share_listings_i_care_about[share_listing_uuid] = time.time()
        request = self.create_request(
            NET_REQUEST_SHARE_LISTING,
            {"sharedir": sharedir, "results_uuid": share_listing_uuid})
        logger.log(TRACE, "requesting share listing from "
                          "peer %r dir %r uuid %r",
                   peer_uuid, sharedir, share_listing_uuid)
        return packb(request)

    def reply_share_listing_cmd(self, peer_uuid, data_block):
        logger.log(TRACE,
                   "replying to share listing request from %r...",
                   peer_uuid)
        reply = self.create_reply(NET_REPLY_SHARE_LISTING, 1)
        try:
            share_dir = data_block["sharedir"]
            share_uuid = data_block["results_uuid"]
        except KeyError:
            logger.error("Improper request (sharedir, results_uuid) "
                         "in %r", data_block)
            # TODO: an unified way of signaling errors.
            reply[NET_DATABLOCK] = 0
            return packb(reply)

        logger.log(TRACE,
                   "Got a share listing request from %r for %r uuid %r",
                   peer_uuid, share_dir, share_uuid)
        with self.app.share_listing_requests_lock:
            if peer_uuid not in self.app.share_listing_requests:
                self.app.share_listing_requests[peer_uuid] = Queue()
            self.app.share_listing_requests[peer_uuid].put(
                (share_dir, share_uuid))
            self.app.filesys.sleep.set()

        return packb(reply)

    def request_share_listing_result_cmd(
            self, sharedir, results_uuid, results):

        logger.log(TRACE, "requesting share listing result "
                          "dir %r uuid %r, %d results",
                   sharedir, results_uuid, len(results))
        request = self.create_request(
            NET_REQUEST_SHARE_LISTING_RESULTS,
            {
                "sharedir": sharedir,
                "results_uuid": results_uuid,
                "results": results
            })
        return packb(request)

    def reply_share_listing_result_cmd(self, peer_uuid, data_block):
        logger.log(TRACE, "replying to request for share listing result "
                          "from peer %r...", peer_uuid)
        reply = self.create_reply(NET_REPLY_SHARE_LISTING_RESULTS, 1)
        try:
            share_dir = data_block["sharedir"]
            share_uuid = data_block["results_uuid"]
            results = data_block["results"]
            with self.app.share_listings_i_care_about_lock:
                assert share_uuid in self.app.share_listings_i_care_about
        except (KeyError, AssertionError):
            logger.error("Improper request (sharedir, results_uuid, "
                         "results) in %r", data_block)
            # TODO: an unified way of signaling errors.
            reply = self.create_reply(NET_REPLY_SHARE_LISTING_RESULTS, 0)
            return packb(reply)

        logger.log(TRACE, "Got %d share listing RESULTS from "
                          "%r for %r (uuid %r)",
                   len(results), peer_uuid, share_dir, share_uuid)
        with self.app.share_listings_lock:
            self.app.share_listings[(peer_uuid, share_dir)] = [
                time.time(), results]
        with self.app.share_listings_i_care_about_lock:
            del self.app.share_listings_i_care_about[share_uuid]

        return packb(reply)

    def request_get_file_chunk_cmd(self, sharedir, filename, offset, chunk_uuid):
        request = self.create_request(
            NET_REQUEST_GET_FILE_CHUNK,
            {
                "sharedir": sharedir,
                "filename": filename,
                "offset": offset,
                "chunk_uuid": chunk_uuid
            })
        logger.log(TRACE,
                   "requesting file chunk from dir "
                   "%r file %r at offset %r uuid %r",
                   sharedir, filename, offset, chunk_uuid)
        return packb(request)

    def reply_get_file_chunk_cmd(self, peer_uuid, data_block):
        try:
            share_dir = data_block["sharedir"]
            file_name = data_block["filename"]
            offset = int(data_block["offset"])
            chunk_uuid = data_block["chunk_uuid"]
        except KeyError:
            logger.error("Improper request (sharedir, filename, "
                         "offset, chunk_uuid) in %r", data_block)
            # TODO: an unified way of signaling errors.
            reply = self.create_reply(
                NET_REPLY_GET_FILE_CHUNK, {"status": 0})
            return packb(reply)

        self.app.filesys.chunk_requests_outgoing_queue.put(
            (peer_uuid, share_dir, file_name, offset, chunk_uuid))
        self.app.filesys.sleep.set()
        reply = self.create_reply(
            NET_REPLY_GET_FILE_CHUNK,
            {"chunk_uuid": chunk_uuid, "status": 1})
        return packb(reply)

    def process_reply_get_file_chunk(self, peer_uuid, data_block):
        try:
            status = data_block["status"]
            chunk_uuid = data_block["chunk_uuid"]
        except KeyError:
            logger.error("Improper request (status, chunk_uuid) in "
                         "%r", data_block)
            # TODO: an unified way of signaling errors.
            return ""

        logger.log(TRACE, "get file chunk %r from peer %r got status %r",
                   chunk_uuid, peer_uuid, status)
        self.app.filesys.chunk_requests_ack_queue.put((peer_uuid, chunk_uuid))
        self.app.filesys.sleep.set()
        return ""

    def request_give_file_chunk_cmd(self, data, chunk_uuid):
        request = self.create_request(
            NET_REQUEST_GIVE_FILE_CHUNK,
            {
                "data": data,
                "chunk_uuid": chunk_uuid
            })
        logger.log(TRACE,
                   "requesting to give file chunk %r of %d bytes",
                   chunk_uuid, len(data))
        return packb(request)

    def reply_give_file_chunk_cmd(self, peer_uuid, data_block):
        logger.log(TRACE, "replying to %r to give file chunk ...", peer_uuid)
        reply = self.create_reply()
        try:
            chunk_uuid = data_block["chunk_uuid"]
            data = data_block["data"]
        except KeyError:
            logger.error("Improper request (chunk_uuid, data) "
                         "in %r", data_block)
            # TODO: an unified way of signaling errors.
            return packb(reply)

        logger.log(TRACE, "sending to %r file chunk %r of %d bytes",
                   peer_uuid, chunk_uuid, data)
        self.app.filesys.chunk_requests_incoming_queue.put(
            (peer_uuid, chunk_uuid, data))
        self.app.filesys.sleep.set()
        return packb(reply)
