# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

import time

from umsgpack import packb
import logging

from ..filesystem.file_request import FileRequestHandler, FileRequest
from ..constants import *

logger = logging.getLogger('tacozmq.cmd')


class StartFileDownload(object):
    """
    Mixin for requesting to start a file transfer.

    The peer that wants a file (caller) from another peer (callee)
    will use its client mechanism to send to other's peer
    server a NET_REQUEST_START_DOWNLOAD request. The callee will
    then check the existence and permissions of that file and will
    reply accordingly.

    If the reply is positive the callee will also prepare its client to send
    the file as chunks to the caller's server (see DoFileDownload).

    """
    def request_start_file_download_cmd(self, file_request):
        """
        Compose the request.

        :param file_request: a FileRequest instance.
        :return: The bytes to send to the wire.
        """
        request = self.create_request(
            NET_REQUEST_START_DOWNLOAD, {
                "fake_path": file_request.fake_path,
            })
        file_request.set_state(TRANSFER_INIT, "contacting peer...")
        packed = packb(request)
        logger.log(TRACE, "request for %r was composed - (%d bytes)",
                   file_request, len(packed))
        return packed

    def reply_start_file_download_cmd(self, peer_id, unpacked):
        """
        Analyse the request and compose the reply.
        """
        logger.log(TRACE, "replying to a request to start file download "
                          "from %r ...", peer_id)
        fake_path = ""
        while True:
            # Get the parameters.
            try:
                fake_path = unpacked["fake_path"]
            except KeyError:
                message = "reply is missing a required field"
                break

            # Create a request out of them on the callee side that mirrors
            # the one on the caller side.
            request = FileRequestHandler(
                app=self.app, peer_id=peer_id, fake_path=fake_path)

            # true path is set only if the path is valid and
            # the file exists.
            if request.true_path is None:
                message = "requested file does not exist"
                break

            # Finally we add this to queue where it will be
            # picked up by a worker thread.
            self.app.add_upload(request)

            # Compose a favorable reply.
            reply = self.create_reply(
                NET_REPLY_START_DOWNLOAD, {
                    "peer_id": peer_id,
                    "fake_path": fake_path,
                    "result": API_OK,
                    "file_size": request.file_size
                })
            logger.log(TRACE, "start file download favorable reply sent to "
                              "%r - (%d bytes)",
                       peer_id, len(reply))
            return reply

        logger.error("Peer %r's request to start a file download could "
                     "not be fulfilled: %s %r", peer_id, message, unpacked)
        return self.create_reply(
            NET_REPLY_START_DOWNLOAD, {
                "fake_path": fake_path,
                "result": API_ERROR,
                "message": message
            })

    def process_reply_start_file_download(self, peer_id, unpacked):
        """ Analyse the reply and update the state accordingly. """

        # Get required arguments.
        try:
            fake_path = unpacked['fake_path']
            result = unpacked['result']
        except KeyError:
            logger.error(
                "Expected fields missing from reply: %r",
                unpacked)
            return None

        # Compute the key for this request.
        key = FileRequest.compute_key(
            peer_id=peer_id, fake_path=fake_path)

        with self.app.downloads_lock:
            # We should find a matching request.
            try:
                request = self.app.downloads[key]
            except KeyError:
                logger.error(
                    "The request from peer %r for file %s was not found in our queue"
                    "the reply was: %r",
                    peer_id, fake_path, unpacked)
                return None

            # The request should be waiting for acknowledgement.
            if request.transfer_state != TRANSFER_INIT:
                logger.warning("Unexpected transfer state %r for %s",
                               request.transfer_state, request)

            # Set new state through the property.
            request.acknowledged = True

            # If the peer refused to send the file set the failed status.
            if result == API_ERROR:
                try:
                    message = unpacked['message']
                except KeyError:
                    message = "Peer refused to provide the file"
                request.failed = True
                request.end_time = time.time()
                request.set_state(TRANSFER_FAILED, message)
                logger.error("The request from peer %r for file %s "
                             "was actively rejected by the peer: %s",
                             peer_id, fake_path, message)
                return None

            # We have a good transfer.
            try:
                file_size = unpacked['file_size']
            except KeyError:
                file_size = -1
                logger.error("response is missing required file_size field")
            request.file_size = file_size
            request.set_state(TRANSFER_ACK, "starting...")
            logger.debug("The request from peer %r for file %s "
                         "of %d bytes was accepted; download is starting.",
                         peer_id, fake_path, file_size)
        return None
