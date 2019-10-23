# -*- coding: utf-8 -*-
"""
Requesting files from peers.
"""
from __future__ import unicode_literals
from __future__ import print_function

import logging
import os
import time

from taco.constants import TRANSFER_ACK, TRANSFER_IN_PROGRESS, TRANSFER_COMPLETED, TRANSFER_FAILED, TRANSFER_INIT
from taco.filesystem import convert_path_to_share
from taco.utils import TextTransferMixin, StateOfTransferMixin

logger = logging.getLogger('tacozmq.file')

# The time (seconds) a caller should wait for acknowledged before
# declaring timeout.
WAIT_FOR_ACK = 10
# The time (seconds) after last chunk a caller should wait for
# acknowledged before declaring timeout.
WAIT_FOR_DATA = 30
# The time (seconds) after a transfer is completed (failed or not)
# before it can be discarded from queue.
WAIT_FOR_DISCARD = 30

# The size of a chunk that is send once.
SIZE_OF_CHUNK = 1024


class FileRequest(TextTransferMixin):
    """
    Class representing a file request.

    Attributes
    ----------

    peer_id : object
        The id of the peer from which we're requesting the file or to
        which we're sending the file.
    fake_path : str
        The path of the file. First element is the
        share name; elements are separated by a `/`.

    """
    def __init__(self, peer_id, fake_path):
        """
        Constructor.

        :param peer_id: The id of the peer from which we're requesting
        the file or to which we're sending the file.
        :param fake_path: The path of the file. First element is the
        share name; elements are separated by a `/`.
        """
        super(FileRequest, self).__init__()
        self.peer_id = peer_id
        self.fake_path = fake_path
        self.downloaded_size = 0
        self.file_size = -1
        self.start_time = time.time()
        self.end_time = -1
        self.file_handle = None
        self.true_path = None
        self.chunks_count = 0

    def __str__(self):
        return "FileRequest(%r, %r)" % (self.peer_id, self.fake_path)

    def __repr__(self):
        return "FileRequest(peer_id=%r, fake_path=%r)" % (
            self.peer_id, self.fake_path)

    @staticmethod
    def compute_key(peer_id, fake_path):
        """ Returns a string that identifies a request based on
        peer and file. """
        return "%r%s" % (peer_id, fake_path)

    @property
    def key(self):
        """ Returns a string that identifies this request. """
        return FileRequest.compute_key(self.peer_id, self.fake_path)

    @property
    def discard_time(self):
        return -1 if self.end_time == -1 \
            else (self.end_time + WAIT_FOR_DISCARD)

    @property
    def discardable(self):
        if self.end_time == -1:
            return False
        else:
            return (self.end_time + WAIT_FOR_DISCARD) < time.time()

    @property
    def acknowledged_time_limit(self):
        assert self.transfer_state == TRANSFER_INIT
        return self.status_time + WAIT_FOR_ACK

    @property
    def acknowledged_timeout(self):
        return self.acknowledged_time_limit < time.time()

    @property
    def data_transfer_time_limit(self):
        assert self.transfer_state in (TRANSFER_IN_PROGRESS, TRANSFER_ACK)
        return self.status_time + WAIT_FOR_DATA

    @property
    def data_transfer_timeout(self):
        return self.data_transfer_time_limit < time.time()

    @StateOfTransferMixin.completed.setter
    def completed(self, value=True):
        if value:
            self.transfer_state = TRANSFER_COMPLETED
            self.status_message = "success"
        else:
            self.transfer_state = TRANSFER_FAILED
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
        self.end_time = time.time()

    @StateOfTransferMixin.failed.setter
    def failed(self, value=True):
        if value:
            self.transfer_state = TRANSFER_FAILED
        else:
            self.transfer_state = TRANSFER_COMPLETED
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
        self.end_time = time.time()


class FileRequestHandler(FileRequest):
    """
    Class representing a file request on the peer that has the file.

    Attributes
    ----------

    true_path : str
        The path of the file with local separators.
    """
    def __init__(self, app, peer_id, fake_path):
        """
        Constructor.

        :param peer_id: The id of the peer from which we're requesting
        the file or to which we're sending the file.
        :param fake_path: The path of the file. First element is the
        share name; elements are separated by a `/`.
        """
        super(FileRequestHandler, self).__init__(peer_id=peer_id, fake_path=fake_path)
        parts = fake_path.split('/')
        true_path = None
        if len(parts) == 0:
            logger.error("empty path")
        else:
            share_path = convert_path_to_share(app, parts[0])
            if len(share_path) == 0:
                logger.error("Unknown share: %s", parts[0])
            else:
                true_path = os.path.join(share_path, *parts[1:])
                if not os.path.isfile(true_path):
                    logger.error("requested file %s does not exist",
                                 true_path)
                    true_path = None
                elif not os.access(true_path, os.R_OK):
                    logger.error("requested file %s exists but is "
                                 "not readable",
                                 true_path)
                    true_path = None
                else:
                    self.file_size = os.path.getsize(true_path)
        self.true_path = true_path
        self.acknowledged = True
        self.file_offset = -1

    def read(self):
        """ Reads the content to be sent and returns a bytes string. """
        assert self.file_handle is not None
        offset = self.file_offset
        try:
            self.file_handle.seek(self.file_offset)
            chunk = self.file_handle.read(SIZE_OF_CHUNK)
            self.file_offset = self.file_offset + len(chunk)
        except OSError:
            self.failed = True
            logger.error("Failed to read %s", self, exc_info=True)
            return None, None, None

        if chunk == b'':
            # We have reached the end of the file.
            self.set_state(TRANSFER_COMPLETED, "upload completed")
            eof = self.chunks_count
            logger.debug("end of file for %s with %d chunks",
                         self, eof)
        else:
            self.status_time = time.time()
            self.chunks_count = self.chunks_count + 1
            eof = -1

        return chunk, offset, eof
