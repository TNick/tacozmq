# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

from umsgpack import packb
import logging
import time
import uuid

from ..constants import *

logger = logging.getLogger('tacozmq.cmd')


class Chat(object):
    """

    """
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
        return reply
