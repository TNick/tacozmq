# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

import time

from umsgpack import packb
import logging
import os

from ..filesystem.file_request import FileRequestHandler, FileRequest
from ..constants import *

logger = logging.getLogger('tacozmq.cmd.file')


class DoFileDownload(object):
    """
    Mixin for transferring a file.

    The peer that wants a file (caller) from another peer (callee)
    will use its client mechanism to send to other's peer
    server a NET_REQUEST_START_DOWNLOAD request. The callee will
    then check the existence and permissions of that file and will
    reply accordingly.

    This mixin deals with the next step: actually transferring the file.
    The roles are reversed here: the caller is the peer that has the file
    and uses its client to send chunks with a NET_REQUEST_DO_DOWNLOAD
    while the callee receives the chunk in its server and acknowledges it
    using NET_REPLY_DO_DOWNLOAD.

    """
    def request_do_file_download_cmd(self, file_request, chunk, offset, eof):
        """
        Compose the request.

        :param file_request: a FileRequest instance.
        :param chunk: the chunk to send.
        :param eof: end of file is -1 if the end of file has not yet
        been reached and is set to the total number of chunks otherwise.
        :return: The bytes to send to the wire.
        """
        request = self.create_request(
            NET_REQUEST_DO_DOWNLOAD, {
                "fake_path": file_request.fake_path,
                "offset": offset,
                "chunk": chunk,
                "eof": eof
            })
        packed = packb(request)
        logger.log(TRACE, "request for %r was composed - (%d bytes)",
                   file_request, len(packed))
        return packed

    def reply_do_file_download_cmd(self, peer_id, unpacked):
        """
        Analyse the request and compose the reply.
        """
        logger.log(TRACE, "replying to a request to upload a file "
                          "from %r ...", peer_id)
        fake_path = ""
        while True:
            # Get the parameters.
            try:
                fake_path = unpacked["fake_path"]
                offset = int(unpacked["offset"])
                chunk = unpacked["chunk"]
                eof = int(unpacked["eof"])
            except (KeyError, ValueError):
                message = "reply is missing a required field or " \
                          "the value is unsuitable"
                break

            # Compute the key for this file_transfer.
            key = FileRequest.compute_key(
                peer_id=peer_id, fake_path=fake_path)

            with self.app.settings_lock:
                download_location = self.app.settings["Download Location"]

            with self.app.download_chunk_lock:
                # We should find a matching file_transfer.
                try:
                    file_transfer = self.app.downloads[key]
                except KeyError:
                    logger.error(
                        "The file_transfer from peer %r for file %s was not found in our queue"
                        "the reply was: %r",
                        peer_id, fake_path, unpacked)
                    return None

                # First one?
                if file_transfer.acknowledged:
                    logger.log(TRACE, "received first package of %d bytes for "
                                      "file %s", len(chunk), file_transfer)

                    if not os.path.isdir(download_location):
                        os.makedirs(download_location)
                        if not os.path.isdir(download_location):
                            message = "no download directory: %r" % \
                                      download_location
                            break

                    parts = file_transfer.fake_path.split('/')
                    id_file = 1
                    file_transfer.true_path = os.path.join(
                        download_location, parts[-1])
                    while os.path.exists(file_transfer.true_path):
                        file_transfer.true_path = os.path.join(
                            download_location,
                            '%s.%d' % (parts[-1], id_file))
                    file_transfer.file_handle = open(
                        file_transfer.true_path, 'w+b')
                elif file_transfer.in_progress:
                    logger.log(TRACE, "received package of %d bytes for "
                                      "file %s", len(chunk), file_transfer)
                elif file_transfer.failed:
                    message = file_transfer.status_message
                    break
                else:
                    message = "invalid state: %r" % file_transfer.transfer_state
                    break

                if eof == -1:
                    # This is not the end-of-file chunk
                    file_transfer.file_handle.seek(offset)
                    file_transfer.file_handle.write(chunk)
                    file_transfer.chunks_count = file_transfer.chunks_count + 1

                    # Set new state.
                    file_transfer.set_state(TRANSFER_IN_PROGRESS, "in progress")
                else:
                    # This is the end of file chunk; eof holds the number of
                    # chunks that were transmitted.
                    if eof != file_transfer.chunks_count:
                        message = "invalid number of parts: " \
                                  "%r received / %r expected" % (
                            file_transfer.chunks_count, eof)
                        break

                    # Sets the time when the transfer has been completed
                    # and closes the file handle. A success message is also
                    # set.
                    file_transfer.completed = True

            # Compose a favorable reply.
            reply = self.create_reply(
                NET_REPLY_DO_DOWNLOAD, {
                    "fake_path": fake_path,
                    "result": API_OK,
                    "offset": offset
                })
            logger.log(TRACE, "file download ack reply at offset %d sent to "
                              "%r - (%d bytes)",
                       offset, peer_id, len(reply))
            return reply

        file_transfer.failed = True
        file_transfer.status_message = message
        logger.error("Peer %r's request to upload a file chunk could "
                     "not be fulfilled: %s %r", peer_id, message, unpacked)
        return self.create_reply(
            NET_REPLY_DO_DOWNLOAD, {
                "fake_path": fake_path,
                "result": API_ERROR,
                "message": message
            })

    def process_reply_do_file_download(self, peer_id, unpacked):
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
                request = self.app.uploads[key]
            except KeyError:
                logger.error(
                    "The request from peer %r for file %s "
                    "was not found in our queue; "
                    "the reply was: %r",
                    peer_id, fake_path, unpacked)
                return None

            # If the peer refused to send the file set the failed status.
            if result == API_ERROR:
                try:
                    message = unpacked['message']
                except KeyError:
                    message = "Peer was unable to process our upload"
                request.failed = True
                request.state_message = message
                logger.error("The request from peer %r for file %s "
                             "was actively rejected by the peer: %s",
                             peer_id, fake_path, message)
                return None

            # We have a good transfer.
            try:
                offset = unpacked['offset']
            except KeyError:
                offset = -1
                logger.error("response is missing required offset field")
            logger.debug("The upload of chunk at offset %d to peer %r for "
                         "file %s was accepted",
                         offset, peer_id, fake_path)
        return None
