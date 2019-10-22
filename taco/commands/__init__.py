# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

from umsgpack import packb, unpackb
import logging

from ..constants import *
from .certs import Certs
from .chat import Chat
from .get_file_chunk import GetFileChunk
from .give_file_chunk import GiveFileChunk
from .rollcall import RollCall
from .share import ShareListing
from .share_result import SharelResult

logger = logging.getLogger('tacozmq.cmd')


class TacoCommands(
        Certs, Chat, GetFileChunk, GiveFileChunk, RollCall,
        ShareListing, SharelResult):
    """
    The class host - for each exchange - the means to create the request
    on the client side, to create the reply on
    the server side and to process that reply on client side.
    """
    def __init__(self, app):
        super(TacoCommands, self).__init__()
        self.app = app
        # for use in process_request()
        self.request_map = {
            NET_REQUEST_ROLLCALL:
                TacoCommands.reply_rollcall_cmd,
            NET_REQUEST_CERTS:
                TacoCommands.reply_certs_cmd,
            NET_REQUEST_CHAT:
                TacoCommands.reply_chat_cmd,
            NET_REQUEST_SHARE_LISTING:
                TacoCommands.reply_share_listing_cmd,
            NET_REQUEST_SHARE_LISTING_RESULTS:
                TacoCommands.reply_share_listing_result_cmd,
            NET_REQUEST_GET_FILE_CHUNK:
                TacoCommands.reply_get_file_chunk_cmd,
            NET_REQUEST_GIVE_FILE_CHUNK:
                TacoCommands.reply_give_file_chunk_cmd,
        }
        # for use in process_reply()
        self.reply_map = {
            NET_REPLY_ROLLCALL:
                TacoCommands.process_reply_rollcall,
            NET_REPLY_CERTS:
                TacoCommands.process_reply_certs,
            NET_REPLY_GET_FILE_CHUNK:
                TacoCommands.process_reply_get_file_chunk,
            NET_REPLY_SHARE_LISTING:
                TacoCommands.process_share_listing_cmd,
        }

    def create_request(self, command=NET_GARBAGE, data=None):
        """ Creates a basic scaffolding for requests. """
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
        """ Creates a basic scaffolding for replies. """
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
        """
        Any data received by the server will be interpreted by this method.

        The method unpacks the data and checks that required fields
        are present in incoming, then uses request_map and the code in the
        request to select a method to handle this reply.

        :param packed: The (decrypted) input in it's raw form.
        :return: (ident, reply) a tuple where ident is the identity where
        the reply should be sent and reply is the packed data. In case of
        errors the ident will be NO_IDENTITY and reply will be None.
        """
        try:
            unpacked = unpackb(packed)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            logger.error("data could not be unpacked", exc_info=True)
            return NO_IDENTITY, None

        try:
            identity = unpacked[NET_IDENT]
            trunk = unpacked[NET_DATABLOCK]
            req_code = unpacked[NET_REQUEST]
        except KeyError:
            logger.error("request is missing a required field", exc_info=True)
            return NO_IDENTITY, None

        logger.log(TRACE, "request from %r to %r payload %r",
                   identity, req_code, trunk)

        # Select the method that replies based on request code.
        try:
            func = self.request_map[req_code]
        except KeyError:
            logger.error("%r used unknown NET_REQUEST code %r: %r",
                           identity, req_code, unpacked)
            return NO_IDENTITY, None

        # execute and return packed data.
        try:
            return identity, packb(func(self, identity, trunk))
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            logger.error("Exception while processing request %r from %r",
                         req_code, identity,
                         exc_info=True)
            return NO_IDENTITY, None

    def process_reply(self, peer_uuid, packed):
        """
        Any data received by the client will be interpreted by this method.

        The method unpacks the data and checks that required fields
        are present in incoming, then uses reply_map and the code in the
        reply to select a method to handle this reply.

        Next request generated by this method, if any, will be placed in
        mediul-priority queue.

        :param peer_uuid: The originator.
        :param packed: The (decrypted) input in it's raw form.
        :return: the next request to send to this peer or None to end
        this dialog. None is also returned in case of errors.
        """
        try:
            unpacked = unpackb(packed)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            logger.error("data could not be unpacked", exc_info=True)
            return None

        try:
            identity = unpacked[NET_IDENT]
            trunk = unpacked[NET_DATABLOCK]
            reply_code = unpacked[NET_REPLY]
        except KeyError:
            logger.error("reply is missing a required field", exc_info=True)
            return None

        logger.log(TRACE, "reply from %r/%r to %r payload %r",
                   identity, peer_uuid, reply_code, trunk)

        # Select the method that replies based on request code.
        try:
            func = self.reply_map[reply_code]
        except KeyError:
            logger.error("%r used unknown NET_REPLY code %r: %r",
                         identity, reply_code, unpacked)
            return None

        # execute and return packed data.
        try:
            return func(self, peer_uuid, trunk)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            logger.error("Exception while processing reply %r from %r",
                         reply_code, peer_uuid,
                         exc_info=True)
            return None
