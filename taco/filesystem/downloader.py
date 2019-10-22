# -*- coding: utf-8 -*-
"""
Requesting files from peers.
"""
from __future__ import unicode_literals
from __future__ import print_function

import logging
import threading

from taco.constants import TRACE
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
        super(FileDownloader, self).__init__(app, name="thTacoFS")

        self.sleep = threading.Event()

    def create(self):
        """ Called at thread start to initialize the state. """
        pass

    def terminate(self):
        """ Called at thread end to free resources. """
        pass

    def execute(self):
        """
        Thread's main function executed in a loop.

        Return False to terminate the thread.
        """
        return True

