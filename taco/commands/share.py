# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

from umsgpack import packb
import logging
import sys
import time

from ..constants import *

logger = logging.getLogger('tacozmq.cmd')
if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue


class SharelListing(object):
    """

    """
    def request_share_listing_cmd(
            self, peer_uuid, sharedir, share_listing_uuid):

        with self.app.share_listings_i_care_about_lock:
            self.app.share_listings_i_care_about[share_listing_uuid] = time.time()
        request = self.create_request(
            NET_REQUEST_SHARE_LISTING,
            {"sharedir": sharedir, "results_uuid": share_listing_uuid})
        logger.log(TRACE, "requesting share listing from "
                          "peer %r dir %r uuid %r",
                   peer_uuid, sharedir, share_listing_uuid)
        return packb(request)

    def reply_share_listing_cmd(self, peer_uuid, data_block):
        logger.log(TRACE,
                   "replying to share listing request from %r...",
                   peer_uuid)
        reply = self.create_reply(NET_REPLY_SHARE_LISTING, 1)
        try:
            share_dir = data_block["sharedir"]
            share_uuid = data_block["results_uuid"]
        except KeyError:
            logger.error("Improper request (sharedir, results_uuid) "
                         "in %r", data_block)
            # TODO: an unified way of signaling errors.
            reply[NET_DATABLOCK] = 0
            return reply

        logger.log(TRACE,
                   "Got a share listing request from %r for %r uuid %r",
                   peer_uuid, share_dir, share_uuid)
        with self.app.share_listing_requests_lock:
            if peer_uuid not in self.app.share_listing_requests:
                self.app.share_listing_requests[peer_uuid] = Queue()
            self.app.share_listing_requests[peer_uuid].put(
                (share_dir, share_uuid))
            self.app.filesys.sleep.set()

        return reply
