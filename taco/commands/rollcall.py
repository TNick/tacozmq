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


class RollCall(object):
    """
    Hart-beat mixin for peers in the network.

    The request is initiated by the client with NET_REQUEST_ROLLCALL
    and no payload. The server replies with NET_REPLY_ROLLCALL

    """
    def request_rollcall_cmd(self):
        request = self.create_request(NET_REQUEST_ROLLCALL, "")
        logger.log(TRACE, "requesting roll call")
        return packb(request)

    def reply_rollcall_cmd(self, peer_uuid, unpacked):
        """
        The client asks us to tell we're alive.

        We reply with a message consisting of our current nickname and the
        peers we know about.
        """
        logger.log(TRACE, "replying to rollcall from %r ...", peer_uuid)
        with self.app.settings_lock:
            peers_i_can_talk_to = self.app.clients.responsive_peer_ids()

        reply = self.create_reply(
            NET_REPLY_ROLLCALL,
            {
                "Nickname": self.app.settings["Nickname"],
                "Peers": peers_i_can_talk_to
            })
        logger.log(TRACE, "rollcall reply sent to %r - %d peers (%d bytes)",
                   peer_uuid, len(peers_i_can_talk_to), len(reply))
        return reply

    def process_reply_rollcall(self, peer_uuid, unpacked):
        """ A server told us it's alive and the peers it knows. """
        try:
            nickname = unpacked['Nickname']
        except KeyError:
            logger.error(
                "Expected field Nickname missing from rollcall reply: %r",
                unpacked)
            return None

        try:
            reply_peers = unpacked['Peers']
        except KeyError:
            logger.error(
                "Expected field Peers missing from rollcall reply: %r",
                unpacked)
            return None

        with self.app.settings_lock:
            peers = self.app.settings["Peers"]
            local_id = self.app.settings["Local UUID"]
            if peer_uuid in peers:
                peer_data = peers[peer_uuid]
                if NICKNAME_CHECKER.match(nickname):
                    try:
                        old_nick = peer_data["nickname"]
                    except KeyError:
                        old_nick = ''

                    if old_nick != nickname:
                        peer_data["nickname"] = nickname
                        self.app.store.save(False)
                        peers = self.app.settings["Peers"]
                        logger.debug("peer %r's nickname updated from %s to %s",
                                     peer_uuid, old_nick, nickname)
                else:
                    logger.error("%r peer has improper nickname %s",
                                 peer_uuid, nickname)

            request_peers = []
            for peer_id in reply_peers:
                if peer_id == local_id:
                    pass
                elif UUID_CHECKER.match(peer_id):
                    if peer_id not in peers:
                        request_peers.append(peer_id)
                else:
                    logger.error("Improper peer id: %r", peer_id)

        if len(request_peers) > 0:
            logger.debug(
                "rollcall reply has %d peers we don't know about: %r",
                len(request_peers), request_peers)
            return self.request_certs_cmd(request_peers)
        else:
            return None
