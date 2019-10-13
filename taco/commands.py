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
from taco.constants import *

if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue


class TacoCommands(object):
    def __init__(self, app):
        super(TacoCommands, self).__init__()
        self.app = app

    def Create_Request(self, command=NET_GARBAGE, data=None):
        with self.app.settings_lock:
            local_uuid = self.app.settings["Local UUID"]
        response = {
            NET_IDENT: local_uuid,
            NET_REQUEST: command,
            NET_DATABLOCK: '' if data is None else data
        }
        return response

    def Create_Reply(self, command=NET_GARBAGE, data=None):
        with self.app.settings_lock:
            local_uuid = self.app.settings["Local UUID"]
        reply = {
            NET_IDENT: local_uuid,
            NET_REPLY: command,
            NET_DATABLOCK: '' if data is None else data
        }
        return reply

    def Proccess_Request(self, packed):
        reply = self.Create_Request()
        try:
            unpacked = unpackb(packed)
            assert NET_DATABLOCK in unpacked
            assert NET_IDENT in unpacked
        except:
            logging.warning("Got a bad request")
            return "0", packb(reply)
        if NET_REQUEST in unpacked:
            if unpacked[NET_REQUEST] == NET_REQUEST_GIVE_FILE_CHUNK:
                if "data" in unpacked[NET_DATABLOCK]:
                    logging.info(
                        "NET_REQUEST (FileChunk DATA): " + str(len(unpacked[NET_DATABLOCK]["data"])))
            else:
                logging.info("NET_REQUEST: " + str(unpacked))
            IDENT = unpacked[NET_IDENT]
            if unpacked[NET_REQUEST] == NET_REQUEST_ROLLCALL:
                return (
                    IDENT, self.Reply_Rollcall())
            if unpacked[NET_REQUEST] == NET_REQUEST_CERTS:
                return (
                    IDENT, self.Reply_Certs(IDENT, unpacked[NET_DATABLOCK]))
            if unpacked[NET_REQUEST] == NET_REQUEST_CHAT:
                return (
                    IDENT, self.Reply_Chat(IDENT, unpacked[NET_DATABLOCK]))
            if unpacked[NET_REQUEST] == NET_REQUEST_SHARE_LISTING:
                return (
                    IDENT, self.Reply_Share_Listing(IDENT, unpacked[NET_DATABLOCK]))
            if unpacked[NET_REQUEST] == NET_REQUEST_SHARE_LISTING_RESULTS:
                return (
                    IDENT, self.Reply_Share_Listing_Result(IDENT, unpacked[NET_DATABLOCK]))
            if unpacked[NET_REQUEST] == NET_REQUEST_GET_FILE_CHUNK:
                return (
                    IDENT, self.Reply_Get_File_Chunk(IDENT, unpacked[NET_DATABLOCK]))
            if unpacked[NET_REQUEST] == NET_REQUEST_GIVE_FILE_CHUNK:
                return (
                    IDENT, self.Reply_Give_File_Chunk(IDENT, unpacked[NET_DATABLOCK]))

        logging.debug("Unknown Request")
        return "0", packb(reply)

    def Process_Reply(self, peer_uuid, packed):
        response = ""
        try:
            unpacked = unpackb(packed)
            assert NET_DATABLOCK in unpacked
            assert NET_IDENT in unpacked
        except:
            logging.debug("Bad Reply")
            return response
        if NET_REPLY in unpacked:
            logging.info("NET_REPLY: " + str(unpacked))
            if unpacked[NET_REPLY] == NET_REPLY_ROLLCALL:
                return self.Process_Reply_Rollcall(
                    peer_uuid, unpacked[NET_DATABLOCK])
            if unpacked[NET_REPLY] == NET_REPLY_CERTS:
                return self.Process_Reply_Certs(
                    peer_uuid, unpacked[NET_DATABLOCK])
            if unpacked[
                NET_REPLY] == NET_REPLY_GET_FILE_CHUNK:
                return self.Process_Reply_Get_File_Chunk(
                    peer_uuid, unpacked[NET_DATABLOCK])

        return response

    def Request_Chat(self, chatmsg):
        output_block = self.Create_Request(NET_REQUEST_CHAT, [time.time(), chatmsg])
        with self.app.chat_log_lock:
            self.app.chat_log.append([self.app.settings["Local UUID"], time.time(), chatmsg])
            with self.app.chat_uuid_lock:
                self.app.chat_uuid = uuid.uuid4().hex
            if len(self.app.chat_log) > CHAT_LOG_MAXSIZE:
                self.app.chat_log = self.app.chat_log[1:]

        self.app.Add_To_All_Output_Queues(packb(output_block))

    def Reply_Chat(self, peer_uuid, datablock):
        logging.debug(str(datablock))
        with self.app.chat_log_lock:
            self.app.chat_log.append([peer_uuid] + datablock)
            with self.app.chat_uuid_lock:
                self.app.chat_uuid = uuid.uuid4().hex
            if len(self.app.chat_log) > CHAT_LOG_MAXSIZE:
                self.app.chat_log = self.app.chat_log[1:]
        reply = self.Create_Reply(NET_REPLY_CHAT, {})
        return packb(reply)

    def Request_Rollcall(self):
        request = self.Create_Request(NET_REQUEST_ROLLCALL, "")
        return packb(request)

    def Reply_Rollcall(self):
        peers_i_can_talk_to = []
        with self.app.settings_lock:
            for peer_uuid in self.app.settings["Peers"].keys():
                if abs(self.app.clients.get_client_last_reply(
                        peer_uuid) - time.time()) < ROLLCALL_TIMEOUT:
                    peers_i_can_talk_to.append(peer_uuid)
        reply = self.Create_Reply(
            NET_REPLY_ROLLCALL,
            [self.app.settings["Nickname"],
             self.app.settings["Local UUID"]] + peers_i_can_talk_to)
        return packb(reply)

    def Process_Reply_Rollcall(self, peer_uuid, unpacked):
        requested_peers = []
        # logging.warning(str(unpacked))
        with self.app.settings_lock:
            new_nickname = unpacked[0]
            if peer_uuid in self.app.settings["Peers"]:
                peer_data = self.app.settings["Peers"][peer_uuid]
                if "nickname" in peer_data:
                    if peer_data["nickname"] != new_nickname:
                        if NICKNAME_CHECKER.match(new_nickname):
                            peer_data["nickname"] = new_nickname
                            self.app.Save_Settings(False)
                else:
                    if NICKNAME_CHECKER.match(new_nickname):
                        peer_data["nickname"] = new_nickname
                        self.app.Save_Settings(False)
                    else:
                        peer_data["nickname"] = "GENERIC NICKNAME"
                        self.app.Save_Settings(False)
            for peer_id in unpacked[1:]:
                if UUID_CHECKER.match(peer_id):
                    if peer_id not in self.app.settings["Peers"].keys() \
                            and peer_id != self.app.settings[ "Local UUID"]:
                        requested_peers.append(peer_id)
        if len(requested_peers) > 0:
            return self.Request_Certs(requested_peers)
        return ""

    def Request_Certs(self, peer_uuids):
        request = self.Create_Request(NET_REQUEST_CERTS, peer_uuids)
        return packb(request)

    def Reply_Certs(self, peer_uuid, datablock):
        reply = self.Create_Reply(NET_REPLY_CERTS, {})
        with self.app.settings_lock:
            for peer_uuid in datablock:
                if peer_uuid in self.app.settings["Peers"]:
                    peer_data = self.app.settings["Peers"][peer_uuid]
                    reply[NET_DATABLOCK][peer_uuid] = [
                        peer_data["nickname"],
                        peer_data["hostname"],
                        peer_data["port"],
                        peer_data["clientkey"],
                        peer_data[ "serverkey"],
                        peer_data["dynamic"]
                    ]
        return packb(reply)

    def Process_Reply_Certs(self, peer_uuid, unpacked):
        response = ""
        logging.debug("Got some new peers to add:" + str(unpacked))
        if type(unpacked) == type({}):
            for peer_id in unpacked.keys():
                if len(unpacked[peer_id]) == 6:
                    (nickname, hostname, port, clientkey, serverkey, dynamic) = \
                        unpacked[peer_id]
                    with self.app.settings_lock:
                        if not peer_id in self.app.settings["Peers"]:
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
                            self.app.Save_Settings(False)

        return response

    def Request_Share_Listing(self, peer_uuid, sharedir, share_listing_uuid):
        with self.app.share_listings_i_care_about_lock:
            self.app.share_listings_i_care_about[share_listing_uuid] = time.time()
        request = self.Create_Request(
            NET_REQUEST_SHARE_LISTING,
            {"sharedir": sharedir, "results_uuid": share_listing_uuid})
        return packb(request)

    def Reply_Share_Listing(self, peer_uuid, datablock):
        reply = self.Create_Reply(NET_REPLY_SHARE_LISTING, 1)
        try:
            sharedir = datablock["sharedir"]
            shareuuid = datablock["results_uuid"]
        except:
            reply[NET_DATABLOCK] = 0
            return packb(reply)

        # logging.debug("Got a share listing request from:
        #   " + peer_uuid + " for: " + sharedir)
        with self.app.share_listing_requests_lock:
            if not peer_uuid in self.app.share_listing_requests:
                self.app.share_listing_requests[peer_uuid] = Queue()
            self.app.share_listing_requests[peer_uuid]\
                .put((sharedir, shareuuid))
            self.app.filesys.sleep.set()

        return packb(reply)

    def Request_Share_Listing_Results(self, sharedir, results_uuid, results):
        request = self.Create_Request(
            NET_REQUEST_SHARE_LISTING_RESULTS,
            {
                "sharedir": sharedir,
                "results_uuid": results_uuid,
                "results": results
            })
        return packb(request)

    def Reply_Share_Listing_Result(self, peer_uuid, datablock):
        reply = self.Create_Reply(NET_REPLY_SHARE_LISTING_RESULTS, 1)
        try:
            sharedir = datablock["sharedir"]
            shareuuid = datablock["results_uuid"]
            results = datablock["results"]
            with self.app.share_listings_i_care_about_lock:
                assert shareuuid in self.app.share_listings_i_care_about
        except:
            reply = self.Create_Reply(NET_REPLY_SHARE_LISTING_RESULTS, 0)
            return packb(reply)

        # logging.debug("Got share listing RESULTS from: " +
        #   peer_uuid + " for: " + sharedir)
        with self.app.share_listings_lock:
            self.app.share_listings[(peer_uuid, sharedir)] = [
                time.time(), results]
        with self.app.share_listings_i_care_about_lock:
            del self.app.share_listings_i_care_about[shareuuid]

        return packb(reply)

    def Request_Get_File_Chunk(self, sharedir, filename, offset, chunk_uuid):
        request = self.Create_Request(
            NET_REQUEST_GET_FILE_CHUNK,
            {
                "sharedir": sharedir,
                "filename": filename,
                "offset": offset,
                "chunk_uuid": chunk_uuid
            })
        return packb(request)

    def Reply_Get_File_Chunk(self, peer_uuid, datablock):
        try:
            sharedir = datablock["sharedir"]
            filename = datablock["filename"]
            offset = int(datablock["offset"])
            chunk_uuid = datablock["chunk_uuid"]
        except:
            reply = self.Create_Reply(
                NET_REPLY_GET_FILE_CHUNK, {"status": 0})
            return packb(reply)
        self.app.filesys.chunk_requests_outgoing_queue.put(
            (peer_uuid, sharedir, filename, offset, chunk_uuid))
        self.app.filesys.sleep.set()
        reply = self.Create_Reply(
            NET_REPLY_GET_FILE_CHUNK,
            {"chunk_uuid": chunk_uuid, "status": 1})
        return packb(reply)

    def Process_Reply_Get_File_Chunk(self, peer_uuid, datablock):
        try:
            status = datablock["status"]
            chunk_uuid = datablock["chunk_uuid"]
        except:
            return ""
        self.app.filesys.chunk_requests_ack_queue.put((
            peer_uuid, chunk_uuid))
        self.app.filesys.sleep.set()
        return ""

    def Request_Give_File_Chunk(self, data, chunk_uuid):
        request = self.Create_Request(
            NET_REQUEST_GIVE_FILE_CHUNK,
            {"data": data, "chunk_uuid": chunk_uuid})
        return packb(request)

    def Reply_Give_File_Chunk(self, peer_uuid, datablock):
        reply = self.Create_Reply()
        try:
            chunk_uuid = datablock["chunk_uuid"]
            data = datablock["data"]
        except:
            return packb(reply)
        logging.debug("Incoming Chunk Processed")
        self.app.filesys.chunk_requests_incoming_queue.put(
            (peer_uuid, chunk_uuid, data))
        self.app.filesys.sleep.set()
        return packb(reply)
