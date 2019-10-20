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
    Obtain certificates from peers unknown to us.

    The rollcall receives from peers the list of their peers. If
    one is found that is unknown to us this exchange is initiated
    to obtain data about those peers.

    The request uses the NET_REQUEST_CERTS and sends as payload the list of
    peers we're interested in. The reply will extract data from the settings
    and send it back as a dictionary, with values being lists of 6 elements.
    """
    def request_certs_cmd(self, peer_uuids):
        request = self.create_request(NET_REQUEST_CERTS, peer_uuids)
        logger.log(TRACE, "requesting certificates call")
        return packb(request)

    def reply_certs_cmd(self, identity, data_block):
        """
        Replies with an associative list of peers.

        The reply we construct will be a dict, with keys being

        """
        result = {}
        with self.app.settings_lock:
            for peer_uuid in data_block:
                if peer_uuid == identity:
                    # We skip the requester.
                    continue

                try:
                    peer_data = self.app.settings["Peers"][peer_uuid]
                except KeyError:
                    logger.debug("requested data about peer %r which is no "
                                 "longer with us", peer_uuid)
                    continue

                result[peer_uuid] = [
                    peer_data["nickname"],
                    peer_data["hostname"],
                    peer_data["port"],
                    peer_data["clientkey"],
                    peer_data["serverkey"],
                    peer_data["dynamic"]
                ]
        return self.create_reply(NET_REPLY_CERTS, result)

    def process_reply_certs(self, identity, unpacked):
        logger.debug("got some new peers to add from %r", identity)
        if not isinstance(unpacked, dict):
            logger.error("expected payload to be dict: %r", unpacked)
            return None

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
            port = int(port)
            dynamic = int(dynamic)
            with self.app.settings_lock:
                if peer_id not in self.app.settings["Peers"]:
                    self.app.settings["Peers"][peer_id] = {
                        "hostname": hostname,
                        "port": port,
                        "clientkey": clientkey,
                        "serverkey": serverkey,
                        "dynamic": int(dynamic),
                        "enabled": 0,
                        "localnick": "",
                        "nickname": nickname
                    }
                    self.app.store.save(False)
                else:
                    peer_data = self.app.settings["Peers"][peer_id]
                    if peer_data["hostname"] != hostname:
                        logger.warning(
                            "peer %r uses for %r hostname %r, we use %r",
                            identity, peer_id, peer_data["hostname"], hostname)
                    if peer_data["port"] != port:
                        logger.warning(
                            "peer %r uses for %r port %r, we use %r",
                            identity, peer_id, peer_data["port"], port)
                    if peer_data["dynamic"] != dynamic:
                        logger.warning(
                            "peer %r uses for %r dynamic %r, we use %r",
                            identity, peer_id, peer_data["dynamic"], dynamic)
                    if peer_data["clientkey"] != clientkey:
                        logger.warning(
                            "peer %r uses for %r clientkey %r, we use %r",
                            identity, peer_id, peer_data["clientkey"], clientkey)
                    if peer_data["serverkey"] != serverkey:
                        logger.warning(
                            "peer %r uses for %r serverkey %r, we use %r",
                            identity, peer_id, peer_data["serverkey"], serverkey)
                    if peer_data["nickname"] != nickname:
                        logger.warning(
                            "peer %r uses for %r nickname %r, we use %r",
                            identity, peer_id, peer_data["nickname"], nickname)

                    logger.log(TRACE, "we know peer %r", peer_id)
        return None
