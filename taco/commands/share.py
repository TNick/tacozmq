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
import os

from ..constants import *

logger = logging.getLogger('tacozmq.cmd')
if sys.version_info < (3, 0):
    from Queue import Queue
else:
    from queue import Queue


class ShareListing(object):
    """
    Get directory listings.

    The request is simply forwarded to file system queue.
    """
    def request_share_listing_cmd(
            self, peer_uuid, sharedir, share_listing_uuid):

        with self.app.share_listings_mine_lock:
            self.app.share_listings_mine[share_listing_uuid] = time.time()
        request = self.create_request(
            NET_REQUEST_SHARE_LISTING,
            {
                "sharedir": sharedir,
                "results_uuid": share_listing_uuid
            }
        )
        logger.log(TRACE, "requesting share listing from "
                          "peer %r dir %r uuid %r",
                   peer_uuid, sharedir, share_listing_uuid)
        return packb(request)

    def reply_share_listing_cmd(self, peer_uuid, data_block):
        logger.log(TRACE,
                   "replying to share listing request from %r...",
                   peer_uuid)

        while True:
            try:
                share_dir = data_block["sharedir"]
                share_uuid = data_block["results_uuid"]
            except KeyError:
                share_uuid = ''
                share_dir = ''
                message = "Required fields missing"
                break
            logger.log(TRACE,
                       "Got a share listing request from %r for %r uuid %r",
                       peer_uuid, share_dir, share_uuid)

            result = []
            share_parts = list(filter(None, share_dir.split('/')))
            if len(share_parts) == 0:
                # Asking for the list of shares
                with self.app.settings_lock:
                    for (share_name, share_path) in self.app.settings["Shares"]:
                        result.append({
                            'name': share_name,
                            'path': share_name,
                            'kind': 'dir'
                       })
            else:
                # TODO: there's no reason shares to be a list;
                # they could be a dict
                # asking about a directory
                b_found, share_path, share_name = False, '', ''
                for (share_name, share_path) in self.app.settings["Shares"]:
                    if share_name == share_parts[0]:
                        b_found = True
                        break
                if not b_found:
                    message = "this peer does not share %s" % share_name
                    break

                current_path = os.path.join(share_path, *share_parts[1:])
                if not os.path.isdir(current_path):
                    message = "the path was not found on the peer"
                    break

                for name in os.listdir(current_path):
                    path = os.path.join(current_path, name)
                    fake_path = '%s/%s' % (share_dir, name)

                    if os.path.isdir(path):
                        kind = 'dir'
                    elif os.path.isfile(path):
                        kind = 'file'
                    else:
                        logger.debug(
                            "%s is neither a file nor a directory",
                            path
                        )
                        continue

                    result.append({
                        'name': name,
                        'path': fake_path,
                        'kind': kind
                    })

            return self.create_reply(
                NET_REPLY_SHARE_LISTING, {
                    "result": API_OK,
                    "share_uuid": share_uuid,
                    "share_dir": share_dir,
                    "data": result
                })

        return self.create_reply(
            NET_REPLY_SHARE_LISTING, {
                "result": API_ERROR,
                "share_uuid": share_uuid,
                "share_dir": share_dir,
                "message": message
            })

        #
        #
        #
        # reply = self.create_reply(NET_REPLY_SHARE_LISTING, 1)
        # try:
        #     share_dir = data_block["sharedir"]
        #     share_uuid = data_block["results_uuid"]
        # except KeyError:
        #     logger.error("Improper request (sharedir, results_uuid) "
        #                  "in %r", data_block)
        #     return reply
        #
        # logger.log(TRACE,
        #            "Got a share listing request from %r for %r uuid %r",
        #            peer_uuid, share_dir, share_uuid)
        # # with self.app.share_listing_requests_lock:
        # #     try:
        # #         peer_queue = self.app.share_listing_requests[peer_uuid]
        # #     except KeyError:
        # #         peer_queue = Queue()
        # #         self.app.share_listing_requests[peer_uuid] = peer_queue
        # #     peer_queue.put((share_dir, share_uuid))
        # #     self.app.filesys.sleep.set()
        #
        # share_dir = share_dir.split('/')
        # if len(share_dir) == 0:
        #     # Asking for the list of shares
        #     with self.app.settings_lock:
        #         for (share_name, share_path) in self.app.settings["Shares"]:
        #
        # else:
        #     # asking about a directory
        #
        # return reply

    def process_share_listing_cmd(self, peer_uuid, data_block):
        try:
            result = data_block["result"]
            share_uuid = data_block["share_uuid"]
            share_dir = data_block["share_dir"]
            if result == API_ERROR:
                logger.error("Received error at share listing request: %r",
                             data_block["message"])
                return None
            else:
                results = data_block["data"]
        except KeyError:
            logger.error("Improper response: %r", data_block)
            return None

        with self.app.share_listings_lock:
            self.app.share_listings[(peer_uuid, share_dir)] = [
                time.time(), results]
        with self.app.share_listings_mine_lock:
            del self.app.share_listings_mine[share_uuid]

        return None
