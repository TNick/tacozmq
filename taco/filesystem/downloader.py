# -*- coding: utf-8 -*-
"""
Requesting files from peers.
"""
from __future__ import unicode_literals
from __future__ import print_function

import logging
import threading
import random
import time

from taco.constants import TRACE, TRANSFER_INIT, TRANSFER_FAILED, TRANSFER_ACK, TRANSFER_IN_PROGRESS, \
    TRANSFER_COMPLETED, PRIORITY_FILE
from taco.thread import TacoSleepThread
from .file_request import FileRequest

logger = logging.getLogger('tacozmq.file')


class FileDownloader(TacoSleepThread):
    """
    Class that performs tasks related to downloading files on the
    requester side.

    The queue for requests is managed by the DownloadManager (self.app).
    It stores FileRequest instances.
    """
    def __init__(self, app):
        """ Constructor. """
        super(FileDownloader, self).__init__(
            app, name="thTacoFileDownloader")

    def create(self):
        """ Called at thread start to initialize the state. """
        pass

    def terminate(self):
        """ Called at thread end to free resources. """
        pass

    def download_not_ack(self, file_transfer):
        """ The transfer has been send to the peer but has
        not been acknowledged, yet."""
        if file_transfer.acknowledged_timeout:
            # The timeout for acknowledge has passed
            # so we declare this a failed transfer.
            logger.error("timeout waiting for peer %r to "
                         "acknowledge download request for "
                         "%s", file_transfer.peer_id, file_transfer.fake_path)
            file_transfer.set_state(
                TRANSFER_FAILED,
                "the peer did not respond in a timely "
                "fashion")

    def download_acknowledged(self, file_transfer):
        """ The transfer has been acknowledged but no chunk has
        been received, yet. """
        if file_transfer.data_transfer_timeout:
            # The timeout for receiving first chunk has passed
            # so we declare this a failed transfer.
            logger.error("timeout waiting for peer to "
                         "send data we request for "
                         "%s", file_transfer)
            file_transfer.set_state(
                TRANSFER_FAILED,
                "the peer did not sent data in a timely "
                "fashion")

    def download_in_progress(self, file_transfer):
        """ The transfer has been acknowledged and at least one chunk has
        been received. """
        if file_transfer.data_transfer_timeout:
            # The timeout for receiving first chunk has passed
            # so we declare this a failed transfer.
            logger.error("timeout waiting for peer to "
                         "send data we request for "
                         "%s", file_transfer)
            file_transfer.set_state(
                TRANSFER_FAILED,
                "the peer sent some data then it stopped")

    def download_completed(self, file_transfer):
        """ The transfer has been completed (successfully or not). """
        if file_transfer.discardable:
            logger.debug("Completed file transfer %s is being "
                         "removed from the downloads queue", file_transfer)
            del self.app.downloads[file_transfer.key]
            del self.app.downloading_peers[file_transfer.peer_id][file_transfer.key]
            if len(self.app.downloading_peers[file_transfer.peer_id]) == 0:
                del self.app.downloading_peers[file_transfer.peer_id]

    def update_downloads(self):
        """ Called once in a while to update the requests we've
        sent to other peers. """
        with self.app.downloads_lock:
            keys = random.sample(
                self.app.downloads.keys(), len(self.app.downloads))

        for key in keys:
            with self.app.downloads_lock:
                # The entry might have been removed meanwhile.
                try:
                    file_transfer = self.app.downloads[key]
                except KeyError:
                    continue

                # These need to be fast state updates as we're keeping the lock
                # on downloads.
                if file_transfer.initial_state:
                    self.download_not_ack(file_transfer)
                elif file_transfer.acknowledged:
                    self.download_acknowledged(file_transfer)
                elif file_transfer.in_progress:
                    self.download_in_progress(file_transfer)
                elif file_transfer.transfer_done:
                    self.download_completed(file_transfer)
                else:
                    assert False, "unknown state %r" % \
                                  file_transfer.transfer_state

    def upload_acknowledged(self, file_transfer):
        """ The transfer has been acknowledged we haven't started the
        process of sending the file. """
        if file_transfer.data_transfer_timeout:
            logger.warning("We haven't sent first package in expected "
                           "time frame; the peer might have been timed out")

        assert file_transfer.file_offset == -1
        file_transfer.file_offset = 0
        try:
            file_transfer.file_handle = open(file_transfer.true_path, "rb")
        except IOError:
            file_transfer.failed = True
            logger.error(
                "The file %s no longer exists or is inaccessible",
                file_transfer)
            return

        file_transfer.set_state(TRANSFER_IN_PROGRESS, "uploading...")

    def upload_in_progress(self, file_transfer):
        """ The transfer has been acknowledged and at least one chunk has
        been sent. """
        if file_transfer.data_transfer_timeout:
            logger.warning("We haven't sent next package in expected "
                           "time frame; the peer might have been timed out")

        with self.app.upload_chunk_lock:
            # Reads next chunk and tests if we have reached the end of the file.
            chunk, offset, eof = file_transfer.read()
            if chunk is None:
                return
            # An empty chunk is sent last with eof parameter indicating
            # the number of chunks we have send. The requester will check
            # this number against the number of chunks it received.

        request = self.app.commands.request_do_file_download_cmd(
            file_transfer, chunk, offset, eof)
        self.app.add_to_output_queue(
            file_transfer.peer_id, request, PRIORITY_FILE)

    def upload_completed(self, file_transfer):
        """ The transfer has been completed (successfully or not). """
        if file_transfer.discardable:
            logger.debug("Completed file transfer %s is being "
                         "removed from the uploads queue", file_transfer)
            if file_transfer.file_handle is not None:
                file_transfer.file_handle.close()
                file_transfer.file_handle = None
            del self.app.uploads[file_transfer.key]
            del self.app.uploading_peers[file_transfer.peer_id][file_transfer.key]
            if len(self.app.uploading_peers[file_transfer.peer_id]) == 0:
                del self.app.uploading_peers[file_transfer.peer_id]

    def update_uploads(self):
        """ Called once in a while to update the upload
        requests we've receive from other peers. """
        with self.app.uploads_lock:
            keys = random.sample(
                self.app.uploads.keys(), len(self.app.uploads))

        for key in keys:
            with self.app.uploads_lock:
                # The entry might have been removed meanwhile.
                try:
                    file_transfer = self.app.uploads[key]
                except KeyError:
                    continue

                # These need to be fast state updates as we're keeping
                # the lock on uploads.
                b_handled = True
                if file_transfer.initial_state:
                    assert False, "The file transfers should only added to " \
                                  "queue after they are " \
                                  "acknowledged by this side"
                elif file_transfer.transfer_done:
                    self.upload_completed(file_transfer)
                elif file_transfer.acknowledged:
                    self.upload_acknowledged(file_transfer)
                else:
                    b_handled = False

            # We release the lock for transfer related tasks.
            if b_handled:
                pass
            elif file_transfer.in_progress:
                self.upload_in_progress(file_transfer)
            else:
                assert False, "unknown state %r" % file_transfer.transfer_state

    def execute(self):
        """
        Thread's main function executed in a loop.

        Return False to terminate the thread.
        """
        self.update_downloads()
        self.update_uploads()
        return True

