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
from taco.globals import TacoApp
from taco.constants import GB
from taco.apis import post_routes
from taco.utils import norm_join, ShutDownException

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
        logging.debug("Completed the shutdown sequence (%d)" %
                      shutdown_counter[0])
        shutdown_counter[0] = shutdown_counter[0] - 1
        if shutdown_counter[0] <= 1:
            logging.debug("Forcing exit using sys.exit...")
            import sys
            sys.exit(0)
        elif shutdown_counter[0] <= 0:
            logging.debug("Forcing exit using os._exit...")
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
        jdata = request.json
        try:
            api_call = jdata
        except:
            return "0"
        if not "action" in jdata:
            return "0"
        if not "data" in jdata:
            return "0"

        action = jdata[u"action"]
        if action in post_routes:
            result = post_routes[action](jdata, app)
            return result

        logging.error("action %s is not part of post routes", action)
        return "-1"

    @result.route('/browselocaldirs/')
    @result.route('/browselocaldirs/<browse_path:path>')
    def index(browse_path="/"):
        browse_path = str(browse_path)
        if platform.system() != 'Windows':
            base_dir = '/'
            if browse_path == "":
                browse_path = base_dir
            elif base_dir != base_dir:
                browse_path = base_dir + browse_path
        else:
            try:
                base_dir = os.environ['HOME']
                if not os.path.isdir(base_dir):
                    logging.debug("%s does not exist", base_dir)
                    base_dir = os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
                    if not os.path.isdir(base_dir):
                        logging.debug("%s does not exist", base_dir)
                        base_dir = os.environ['PUBLIC']
                        if not os.path.isdir(base_dir):
                            logging.debug("%s does not exist", base_dir)
                            from pathlib import Path
                            base_dir = str(Path.home())
                            if not os.path.isdir(base_dir):
                                raise RuntimeError("Cannot find a path to present")

                if browse_path == "":
                    browse_path = base_dir
                else:
                    browse_path = os.path.join(base_dir, browse_path)
            except Exception:
                browse_path = ""
        try:
            logging.debug("Listing directories in %s", browse_path)
            contents = os.listdir(browse_path)
        except (FileNotFoundError, PermissionError):
            contents = []

        final_contents = []
        for item in contents:
            try:
                if os.path.isdir(os.path.join(browse_path, item)):
                    final_contents.resultend(item)
            except Exception:
                continue
        final_contents.sort()

        return json.dumps(final_contents)

    @result.route('/get/<what>')
    def get__data(what):
        output = ""
        logging.debug("Route -- Getting your: " + what)
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
                from taco.filesystem import Get_Free_Space
                (free, total) = Get_Free_Space(down_dir)
                if free == 0 and total == 0:
                    output = 0.0
                else:
                    output = free / GB
        return str(output)

    return result
