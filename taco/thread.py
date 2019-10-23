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
    """
    A thread with name and a stop event.

    Attributes
    ----------

    app : TacoApp
        Parent application.
    stop : threading.Event
        Event that informs us we should exit thread loop.
    status_lock : threading.Lock
        Guards the access to the status of the thread.
    status : str
        Last major action performed by this thread.
    status_time : float
        The moment when last status was recorded (-1 if never).
    """
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

    def create(self):
        """ Called at thread start to initialize the state. """
        pass

    def terminate(self):
        """ Called at thread end to free resources. """
        pass

    def execute(self):
        """
        Called to execute the main part of the thread.

        In implementations where this function is executed in a loop
        it is expected to return False to break the loop end terminate
        the thread.
        """
        return False

    def run(self):
        """ Thread main function. """
        self.create()
        self.execute()
        self.terminate()


class TacoSleepThread(TacoThread):
    """
    A thread with name, a stop event and a sleep event.

    Attributes
    ----------

    sleep : threading.Event
        Event that prevents the runner from sleeping.
    """
    def __init__(self, app, name, sleep_time=0.2):
        super().__init__(app=app, name=name)
        self.sleep = threading.Event()
        self.sleep_time = sleep_time

    def run(self):
        """ Thread main function. """
        self.create()

        while not self.stop.is_set():
            # Will sleep for sleep_time seconds if the event is
            # not set, otherwise will return right away.
            self.sleep.wait(self.sleep_time)
            self.sleep.clear()

            # Check for our exit condition.
            if self.stop.is_set():
                break

            # Execute the main part of the code.
            if not self.execute():
                break

        self.terminate()
