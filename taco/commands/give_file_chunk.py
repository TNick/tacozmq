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


class GiveFileChunk(object):
    """

    """
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
            return reply

        logger.log(TRACE, "sending to %r file chunk %r of %d bytes",
                   peer_uuid, chunk_uuid, data)
        self.app.filesys.chunk_requests_incoming_queue.put(
            (peer_uuid, chunk_uuid, data))
        self.app.filesys.sleep.set()
        return reply
