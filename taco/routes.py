# -*- coding: utf-8 -*-
"""
Routes for our simple bottle http server.
"""
from __future__ import unicode_literals
from __future__ import print_function

import platform
import re
import os
import uuid
import logging
import json
import sys

from bottle import Bottle, static_file, template, request
from taco.constants import GB, API_ERROR, API_OK
from taco.apis import post_routes, handle_api_call
from taco.filesystem import get_windows_root_directories
from taco.utils import norm_join, ShutDownException

logger = logging.getLogger('tacozmq.app')
if sys.version_info > (3, 0):
    unicode = str


def create_bottle(app):
    result = Bottle()

    # Sometimes the application refuses to terminate so we
    # have some counter-measures in shut_down()
    shutdown_counter = [5]

    # static content
    @result.route('/static/<filename:path>')
    def send_file(filename):
        return static_file(
            filename, root=norm_join(os.getcwd(), 'static'))

    # terminate
    @result.route('/shutitdown')
    def shut_down():
        result.close()
        app.proper_exit()
        if app.cherry is not None:
            app.cherry.stop()
            app.cherry = None
        logger.debug("Completed the shutdown sequence (%d)" %
                      shutdown_counter[0])
        shutdown_counter[0] = shutdown_counter[0] - 1
        if shutdown_counter[0] <= 1:
            logger.debug("Forcing exit using sys.exit...")
            import sys
            sys.exit(0)
        elif shutdown_counter[0] <= 0:
            logger.debug("Forcing exit using os._exit...")
            import os
            os._exit(0)

    # template routes
    @result.route('/')
    def index():
        app.settings_lock.acquire()
        local_settings_copy = app.settings.copy()
        app.settings_lock.release()
        return template('templates/home.tpl', local_settings_copy)

    @result.route('/<name>.taco')
    def taco_page(name):
        app.settings_lock.acquire()
        local_settings_copy = app.settings.copy()
        if name == 'settings':
            local_keys_copy = app.public_keys.copy()
        else:
            local_keys_copy = None
        app.settings_lock.release()

        return template('templates/%s.tpl' % name,
                        local_settings_copy=local_settings_copy,
                        local_keys_copy=local_keys_copy)

    @result.post('/api.post')
    def post_index():
        return handle_api_call(app, request.json)

    @result.route('/browselocaldirs/')
    @result.route('/browselocaldirs/<browse_path:path>')
    def index(browse_path='/'):
        """
        Presents the content of a directory.


        :param browse_path: The path to list.
        :return: A json representation of the reply.
        """
        if len(browse_path) == 0:
            browse_path = '/'

        while True:
            if request.remote_addr != "127.0.0.1":
                message = "Due to security concerns listing of local " \
                           "directories is prohibited"
                break

            try:
                listing = []
                if (platform.system() == 'Windows') and (browse_path == '/'):
                    listing = get_windows_root_directories()
                else:
                    if not os.path.isdir(browse_path):
                        message = "No such path: %s" % browse_path
                        break

                    for item in os.listdir(browse_path):
                        path = os.path.join(browse_path, item)
                        listing.append({
                            'name': item,
                            'path': path,
                            'kind': 'dir' if os.path.isdir(path)
                                    else 'file' if os.path.isfile(path)
                                    else 'unknown'
                        })

                return json.dumps({
                    "result": API_OK,
                    "data": listing
                })
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                message = "exception while browsing local paths"
                logger.exception(message)

            break

        logger.error("failed to browse", message)
        return json.dumps({
            "result": API_ERROR,
            "message": message
        })

        #
        # browse_path = str(browse_path)
        # if platform.system() != 'Windows':
        #     base_dir = '/'
        #     if browse_path == "":
        #         browse_path = base_dir
        #     elif base_dir != base_dir:
        #         browse_path = base_dir + browse_path
        # else:
        #     try:
        #         base_dir = os.environ['HOME']
        #         if not os.path.isdir(base_dir):
        #             logger.debug("%s does not exist", base_dir)
        #             base_dir = os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
        #             if not os.path.isdir(base_dir):
        #                 logger.debug("%s does not exist", base_dir)
        #                 base_dir = os.environ['PUBLIC']
        #                 if not os.path.isdir(base_dir):
        #                     logger.debug("%s does not exist", base_dir)
        #                     from pathlib import Path
        #                     base_dir = str(Path.home())
        #                     if not os.path.isdir(base_dir):
        #                         raise RuntimeError("Cannot find a path to present")
        #
        #         if browse_path == "":
        #             browse_path = base_dir
        #         else:
        #             browse_path = os.path.join(base_dir, browse_path)
        #     except Exception:
        #         browse_path = ""
        # try:
        #     logger.debug("Listing directories in %s", browse_path)
        #     contents = os.listdir(browse_path)
        # except (FileNotFoundError, PermissionError):
        #     contents = []
        #
        # final_contents = []
        # for item in contents:
        #     try:
        #         if os.path.isdir(os.path.join(browse_path, item)):
        #             final_contents.resultend(item)
        #     except Exception:
        #         continue
        # final_contents.sort()
        #
        # return json.dumps(final_contents)

    @result.route('/get/<what>')
    def get__data(what):
        output = ""
        logger.debug("Route -- Getting your: " + what)
        if what == "uuid":
            return uuid.uuid4().hex
        if what == "ip":

            if sys.version_info < (3, 0):
                from urllib import urlopen
                data = urlopen("http://checkip.dyndns.org/").read()
            else:
                from urllib.request import urlopen
                with urlopen("http://checkip.dyndns.org/") as url:
                    data = str(url.read())

            m = re.match(r'.*Current IP Address: (.*)</body>', data)
            if m:
                output = m.group(1)
        if what == "diskfree":
            with app.settings_lock:
                down_dir = app.settings["Download Location"]
            if os.path.isdir(down_dir):
                from taco.filesystem import get_free_space
                (free, total) = get_free_space(down_dir)
                if free == 0 and total == 0:
                    output = 0.0
                else:
                    output = free / GB
        return str(output)

    return result
