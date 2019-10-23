# -*- coding: utf-8 -*-
"""
Small functions that are needed in several parts.
"""
import os
import threading
import time

import zmq
from zmq.utils.monitor import recv_monitor_message
import logging

from .constants import TRACE, TRANSFER_COMPLETED, TRANSFER_FAILED, TRANSFER_IN_PROGRESS, TRANSFER_ACK, TRANSFER_INIT


def norm_path(inp):
    """ Converts input path into an absolute, normalized path. """
    return os.path.normpath(os.path.abspath(inp))


def norm_join(*args):
    """ Like os.path.join but also normalizes the path. """
    return norm_path(os.path.join(*args))


class ShutDownException(Exception):
    pass


def event_monitor(monitor):
    logger = logging.getLogger('tacozmq.zmq')
    event_map = {}
    logger.debug("event names:")
    for name in dir(zmq):
        if name.startswith('EVENT_'):
            value = getattr(zmq, name)
            event_map[value] = name

    # If you need an enumeration of all available events uncomment
    # the block below.
    # if logger.level <= logging.DEBUG:
    #     logger.debug("Events to values:\n%s",
    #                  '\n'.join(['- %40s : %-5i' % (event_map[value], value)
    #                             for value in sorted(event_map.keys())]))

    try:
        while monitor.poll():
            evt = recv_monitor_message(monitor)
            evt.update({'description': event_map[evt['event']]})
            logger.log(TRACE, "Event: %r", evt)
            if evt['event'] == zmq.EVENT_MONITOR_STOPPED:
                break
    except zmq.error.ContextTerminated:
        pass

    monitor.close()
    logger.debug("event monitor thread done!")


class StateOfTransferMixin(object):
    """ Mixin that provides state storage and some properties. """
    def __init__(self):
        """ Constructor. """
        super(StateOfTransferMixin, self).__init__()
        self.transfer_state = TRANSFER_INIT

    @property
    def initial_state(self):
        return self.transfer_state == TRANSFER_INIT

    @property
    def acknowledged(self):
        return self.transfer_state == TRANSFER_ACK

    @acknowledged.setter
    def acknowledged(self, value=True):
        if value:
            self.transfer_state = TRANSFER_ACK
        else:
            self.transfer_state = TRANSFER_INIT

    @property
    def completed(self):
        return self.transfer_state == TRANSFER_COMPLETED

    @completed.setter
    def completed(self, value=True):
        if value:
            self.transfer_state = TRANSFER_COMPLETED
        else:
            self.transfer_state = TRANSFER_FAILED

    @property
    def in_progress(self):
        return self.transfer_state == TRANSFER_IN_PROGRESS

    @in_progress.setter
    def in_progress(self, value=True):
        if value:
            self.transfer_state = TRANSFER_IN_PROGRESS
        else:
            self.transfer_state = TRANSFER_ACK

    @property
    def failed(self):
        return self.transfer_state == TRANSFER_FAILED

    @failed.setter
    def failed(self, value=True):
        if value:
            self.transfer_state = TRANSFER_FAILED
        else:
            self.transfer_state = TRANSFER_COMPLETED

    @property
    def transfer_done(self):
        return self.transfer_state in (
            TRANSFER_FAILED, TRANSFER_COMPLETED)


class TextStateMixin(object):
    """ Mixin that provides textual state storage
    and some properties. """
    def __init__(self):
        """ Constructor. """
        super(TextStateMixin, self).__init__()
        self._status_message = ""
        self.status_time = -1

    @property
    def status_message(self):
        return self._status_message

    @status_message.setter
    def status_message(self, value):
        self._status_message = value
        self.status_time = time.time()


class TextTransferMixin(StateOfTransferMixin, TextStateMixin):
    """ Mixin that provides textual state storage
    and some properties. """
    def __init__(self):
        """ Constructor. """
        super(TextTransferMixin, self).__init__()

    def set_state(self, code, message):
        """ Sets both the code and the message. """
        self.status_message = message
        self.transfer_state = code
