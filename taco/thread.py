# -*- coding: utf-8 -*-
"""
"""
from __future__ import unicode_literals
from __future__ import print_function

import logging
import threading
import time

logger = logging.getLogger('tacozmq.thread')


class TacoThread(threading.Thread):
    def __init__(self, app, name):
        threading.Thread.__init__(self, name=name)
        self.app = app
        # Set this to terminate the thread.
        self.stop = threading.Event()

        self.status_lock = threading.Lock()
        self.status = ""
        self.status_time = -1

    def set_status(self, text, level=logging.DEBUG):
        logger.log(level, text)
        with self.status_lock:
            self.status = text
            self.status_time = time.time()

    def get_status(self):
        with self.status_lock:
            return self.status, self.status_time
