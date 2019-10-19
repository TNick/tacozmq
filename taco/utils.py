# -*- coding: utf-8 -*-
"""
Small functions that are needed in several parts.
"""
import os
import zmq
from zmq.utils.monitor import recv_monitor_message
import logging

from .constants import TRACE


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
