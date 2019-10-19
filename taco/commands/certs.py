# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

from umsgpack import packb
import logging

from ..constants import *

logger = logging.getLogger('tacozmq.cmd')


class Certs(object):
    """

    """
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
        return reply

    def process_reply_certs(self, peer_uuid, unpacked):
        response = None
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
