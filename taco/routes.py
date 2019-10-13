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

import taco.bottle as bottle
from taco.globals import TacoApp
from taco.constants import GB
from taco.apis import post_routes


if sys.version_info > (3, 0):
    unicode = str


# static content
@bottle.route('/static/<filename:path>')
def send_file(filename):
    return bottle.static_file(
        filename, root=os.path.normpath(os.getcwd() + '/static/'))


# terminate
@bottle.route('/shutitdown')
def taco_page():
    TacoApp.instance.proper_exit(1, 1)
    return


# template routes
@bottle.route('/')
def index():
    return bottle.template('templates/home.tpl')


@bottle.route('/<name>.taco')
def taco_page(name):
    return bottle.template('templates/' + str(name) + '.tpl')


@bottle.post('/api.post')
def index():
    jdata = bottle.request.json
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
        result = post_routes[action](jdata)
        return result

    logging.error("action %s is not part of post routes", action)
    return "-1"


@bottle.route('/browselocaldirs/')
@bottle.route('/browselocaldirs/<browse_path:path>')
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
                final_contents.append(item)
        except Exception:
            continue
    final_contents.sort()

    return json.dumps(final_contents)


@bottle.route('/get/<what>')
def getData(what):
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
        app = TacoApp.instance
        with app.settings_lock:
            down_dir = TacoApp.instance.settings["Download Location"]
        if os.path.isdir(down_dir):
            from taco.filesystem import Get_Free_Space
            (free, total) = Get_Free_Space(down_dir)
            if free == 0 and total == 0:
                output = 0.0
            else:
                output = free / GB
    return str(output)
