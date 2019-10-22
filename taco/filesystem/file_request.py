# -*- coding: utf-8 -*-
"""
Requesting files from peers.
"""
from __future__ import unicode_literals
from __future__ import print_function

import logging
import os
import time

from taco.constants import TRANSFER_ACK, TRANSFER_IN_PROGRESS
from taco.filesystem import convert_path_to_share
from taco.utils import TextTransferMixin

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
        assert self.status_message == TRANSFER_ACK
        return self.status_time + WAIT_FOR_ACK

    @property
    def acknowledged_timeout(self):
        return self.acknowledged_time_limit < time.time()

    @property
    def data_transfer_time_limit(self):
        assert self.status_message == TRANSFER_IN_PROGRESS
        return self.status_time + WAIT_FOR_ACK

    @property
    def data_transfer_timeout(self):
        return self.data_transfer_time_limit < time.time()


class FileRequestHandler(FileRequest):
    """
    Class representing a file request on the peer that has the file.
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
                    logger.error("requested file does not exist: %s",
                                 true_path)
                    true_path = None
                else:
                    self.file_size = os.path.getsize(true_path)
        self.true_path = true_path
        self.acknowledged = True

