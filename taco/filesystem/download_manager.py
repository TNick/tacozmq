# -*- coding: utf-8 -*-
"""
Requesting files from peers.
"""
from __future__ import unicode_literals
from __future__ import print_function

import logging
import threading

from taco.constants import TRACE, TRANSFER_ACK
from .file_request import FileRequest, FileRequestHandler

logger = logging.getLogger('tacozmq.file')


class DownloadManager(object):
    """
    Class that manages file download requests.

    Attributes
    ----------

    downloads_lock : threading.Lock
        Guards the access to the list of files that we download
        and related resources.
    downloads : list
        a list of FileRequest
    """

    def __init__(self):
        """ Constructor. """
        super(DownloadManager, self).__init__()

        # We use these to send requests for file
        # downloads to our peers.
        self.downloads_lock = threading.Lock()
        self.downloads = {}
        self.downloading_peers = {}

        # We use these to send requests for file
        # downloads to our peers.
        self.uploads_lock = threading.Lock()
        self.uploads = {}
        self.uploading_peers = {}

        # Actual file transfer.
        self.upload_chunk_lock = threading.Lock()
        self.download_chunk_lock = threading.Lock()

    def add_download(self, peer_id, fake_path):
        """
        Adds a single file to download queue.

        :param peer_id: The id of the peer where this file is located.
        :param fake_path: The path of the file. First element is the
        share name; elements are separated by a `/`.
        :return: FileRequest if the record was added or it already exists,
        None otherwise.
        """
        logger.log(TRACE, "Adding a new file download request: "
                          "peer_id=%r, fake_path=%s", peer_id, fake_path)
        request = FileRequest(peer_id=peer_id, fake_path=fake_path)
        with self.downloads_lock:
            if request.key in self.downloads:
                logger.error("File %s of peer %r is already being downloaded",
                             fake_path, peer_id)
                return self.downloads[request.key]

            # We're adding this structure to our lists.
            self.downloads[request.key] = request
            if peer_id in self.downloading_peers:
                peer_downloads = self.downloading_peers[peer_id]
            else:
                peer_downloads = {}
                self.downloading_peers[peer_id] = peer_downloads
            peer_downloads[request.key] = request

        logger.debug("Request %r was added", request)
        return request

    def rem_download(self, peer_id=None, fake_path=None, request=None):
        """
        Removes a request from download queue.

        :param peer_id: The id of the peer where this file is located.
        Can be None, in which case `request` is required.
        :param fake_path: The path of the file. First element is the
        share name; elements are separated by a `/`.
        Can be None, in which case `request` is required.
        :param request: The request to remove; if None the key will be computed
        from `peer_id` and `fake_path`.
        """

        if request is None:
            if (peer_id is None) or (fake_path is None):
                raise ValueError("peer_id and fake_path are required")
            key = FileRequest.compute_key(
                peer_id=peer_id, fake_path=fake_path)
        else:
            if (peer_id is not None) or (fake_path is not None):
                raise ValueError("peer_id and fake_path are ignored")
            key = request.key
            peer_id, fake_path = request.peer_id, request.fake_path

        with self.downloads_lock:
            if key not in self.downloads:
                logger.error("The requested entry (peer_id=%r, fake_path=%s)"
                             "could not be located in the queue",
                             peer_id, fake_path)
                try:
                    request = self.downloading_peers[peer_id][key]
                    assert False, "Inconsistency detected in download queue"
                except KeyError:
                    pass
                return False

            request = self.downloads[key]
            peer_queue = self.downloading_peers[peer_id]
            del peer_queue[key]
            del self.downloads[key]

        if request.acknowledged:
            if request.completed:
                logger.log(TRACE, "Removed a completed file")
            else:
                logger.error("Removed an acknowledged file that wan not "
                             "yet completed (%r / %r)",
                             request.downloaded_size, request.file_size)
        else:
            logger.debug("Removed a file that was not yet acknowledged")

    def add_upload(self, request):
        """
        Adds a single file to upload queue.

        :param request: The request we want to add.
        """
        logger.log(TRACE, "Adding a new file upload request: "
                          "peer_id=%r, fake_path=%s",
                   request.peer_id, request.fake_path)
        request.set_state(TRANSFER_ACK, "ready to upload")

        with self.uploads_lock:
            if request.key in self.uploads:
                logger.error("File %s of peer %r is already being uploaded",
                             request.fake_path, request.peer_id)
                return self.uploads[request.key]

            # We're adding this structure to our lists.
            self.uploads[request.key] = request
            if request.peer_id in self.uploading_peers:
                peer_uploads = self.uploading_peers[request.peer_id]
            else:
                peer_uploads = {}
                self.uploading_peers[request.peer_id] = peer_uploads
            peer_uploads[request.key] = request

        logger.debug("Request %r was added", request)
        return request

    def rem_upload(self, peer_id=None, fake_path=None, request=None):
        """
        Removes a request from upload queue.

        :param peer_id: The id of the peer where this file is to be sent.
        Can be None, in which case `request` is required.
        :param fake_path: The path of the file. First element is the
        share name; elements are separated by a `/`.
        Can be None, in which case `request` is required.
        :param request: The request to remove; if None the key will be computed
        from `peer_id` and `fake_path`.
        """

        if request is None:
            if (peer_id is None) or (fake_path is None):
                raise ValueError("peer_id and fake_path are required")
            key = FileRequest.compute_key(
                peer_id=peer_id, fake_path=fake_path)
        else:
            if (peer_id is not None) or (fake_path is not None):
                raise ValueError("peer_id and fake_path are ignored")
            key = request.key
            peer_id, fake_path = request.peer_id, request.fake_path

        with self.uploads_lock:
            if key not in self.uploads:
                logger.error("The requested entry (peer_id=%r, fake_path=%s)"
                             "could not be located in the queue",
                             peer_id, fake_path)
                try:
                    request = self.uploading_peers[peer_id][key]
                    assert False, "Inconsistency detected in upload queue"
                except KeyError:
                    pass
                return False

            request = self.uploads[key]
            peer_queue = self.uploading_peers[peer_id]
            del peer_queue[key]
            del self.uploads[key]

        if request.acknowledged:
            if request.completed:
                logger.log(TRACE, "Removed a completed file")
            else:
                logger.error("Removed an acknowledged file that wan not "
                             "yet completed (%r / %r)",
                             request.uploaded_size, request.file_size)
        else:
            logger.debug("Removed a file that was not yet acknowledged")
