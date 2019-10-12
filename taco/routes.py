import taco.bottle as bottle
import taco.settings
import taco.globals
import taco.constants
import taco.filesystem
import taco.commands
from taco.apis import post_routes
import re
import os
import uuid
import logging
import json
import sys

if sys.version_info > (3, 0):
    unicode = str



# static content
@bottle.route('/static/<filename:path>')
def send_file(filename):
    return bottle.static_file(filename, root=os.path.normpath(os.getcwd() + '/static/'))


# terminate
@bottle.route('/shutitdown')
def taco_page():
    taco.globals.properexit(1, 1)
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
    if browse_path == "": browse_path = "/"
    browse_path = "/" + browse_path
    browse_path = unicode(browse_path)
    contents = os.listdir(browse_path)
    final_contents = []
    for item in contents:
        try:
            if os.path.isdir(os.path.join(browse_path, item)): final_contents.append(item)
        except:
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
        with taco.globals.settings_lock:
            down_dir = taco.globals.settings["Download Location"]
        if os.path.isdir(down_dir):
            (free, total) = taco.filesystem.Get_Free_Space(down_dir)
            if free == 0 and total == 0:
                output = 0.0
            else:
                output = free / taco.constants.GB
    return str(output)
