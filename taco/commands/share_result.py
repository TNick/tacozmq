# -*- coding: utf-8 -*-
"""
Request-reply commands used by the api and app.
"""
from __future__ import unicode_literals
from __future__ import print_function

from umsgpack import packb
import logging
import time

from ..constants import *

logger = logging.getLogger('tacozmq.cmd')


class SharelResult(object):
    """

    """
    def request_share_listing_result_cmd(
            self, sharedir, results_uuid, results):

        logger.log(TRACE, "requesting share listing result "
                          "dir %r uuid %r, %d results",
                   sharedir, results_uuid, len(results))
        request = self.create_request(
            NET_REQUEST_SHARE_LISTING_RESULTS,
            {
                "sharedir": sharedir,
                "results_uuid": results_uuid,
                "results": results
            })
        return packb(request)

    def reply_share_listing_result_cmd(self, peer_uuid, data_block):
        logger.log(TRACE, "replying to request for share listing result "
                          "from peer %r...", peer_uuid)
        reply = self.create_reply(NET_REPLY_SHARE_LISTING_RESULTS, 1)
        try:
            share_dir = data_block["sharedir"]
            share_uuid = data_block["results_uuid"]
            results = data_block["results"]
            with self.app.share_listings_i_care_about_lock:
                assert share_uuid in self.app.share_listings_i_care_about
        except (KeyError, AssertionError):
            logger.error("Improper request (sharedir, results_uuid, "
                         "results) in %r", data_block)
            # TODO: an unified way of signaling errors.
            reply = self.create_reply(NET_REPLY_SHARE_LISTING_RESULTS, 0)
            return reply

        logger.log(TRACE, "Got %d share listing RESULTS from "
                          "%r for %r (uuid %r)",
                   len(results), peer_uuid, share_dir, share_uuid)
        with self.app.share_listings_lock:
            self.app.share_listings[(peer_uuid, share_dir)] = [
                time.time(), results]
        with self.app.share_listings_i_care_about_lock:
            del self.app.share_listings_i_care_about[share_uuid]

        return reply
