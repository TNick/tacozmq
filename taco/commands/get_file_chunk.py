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


class GetFileChunk(object):
    """

    """
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
            return reply

        self.app.filesys.chunk_requests_outgoing_queue.put(
            (peer_uuid, share_dir, file_name, offset, chunk_uuid))
        self.app.filesys.sleep.set()
        reply = self.create_reply(
            NET_REPLY_GET_FILE_CHUNK,
            {"chunk_uuid": chunk_uuid, "status": 1})
        return reply

    def process_reply_get_file_chunk(self, peer_uuid, data_block):
        try:
            status = data_block["status"]
            chunk_uuid = data_block["chunk_uuid"]
        except KeyError:
            logger.error("Improper request (status, chunk_uuid) in "
                         "%r", data_block)
            # TODO: an unified way of signaling errors.
            return None

        logger.log(TRACE, "get file chunk %r from peer %r got status %r",
                   chunk_uuid, peer_uuid, status)
        self.app.filesys.chunk_requests_ack_queue.put((peer_uuid, chunk_uuid))
        self.app.filesys.sleep.set()
        return None
