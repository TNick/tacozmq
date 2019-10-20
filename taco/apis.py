# -*- coding: utf-8 -*-
"""
`/api.post` route receives a json string that gets converted to a dict.
All such calls are required to have an action parameter.
For each action this module needs to define a function
wrapped by @post_route("action"). These handlers get collected in
`post_routes` which is then used in routes.py to handle the call.
"""
from __future__ import unicode_literals
from __future__ import print_function
import time
import os
import uuid
import logging
import json
import sys
from collections import defaultdict

from taco.globals import TacoApp
from taco.constants import (
    FILESYSTEM_WORKINPROGRESS_SUFFIX, TRACE, API_ERROR, PRIORITY_MEDIUM
)

logger = logging.getLogger('tacozmq.apis')
if sys.version_info > (3, 0):
    unicode = str


# This is where we collect all paths.
post_routes = {}


def post_route(action):
    """ Wrapper we use to collect all paths in a single dict. """
    def wrap(f):
        def wrapped_f(*args, **kwargs):
            logger.log(TRACE, "servicing %s ...", action)
            result = f(*args, **kwargs)
            if result is None:
                result = "-1"
            elif isinstance(result, int):
                result = str(result)
            elif not isinstance(result, str):
                result = json.dumps(result)
            logger.log(TRACE, "result for %s is: %s", action, result)
            return result

        post_routes[action] = wrapped_f
        return wrapped_f

    return wrap


@post_route("apistatus")
def api_status(jdata, app):
    return {"status": 1}


@post_route("threadstatus")
def thread_status(jdata, app):

    output = {"threads": {}}
    output["threads"]["clients"] = {}
    output["threads"]["server"] = {}

    output["threads"]["clients"]["alive"] = app.clients.is_alive()
    (output["threads"]["clients"]["status"],
     output["threads"]["clients"]["lastupdate"]) = \
        app.clients.get_status()
    output["threads"]["clients"]["lastupdate"] = abs(
        time.time() - float(output["threads"]["clients"]["lastupdate"]))

    output["threads"]["server"]["alive"] = app.server.is_alive()
    (output["threads"]["server"]["status"],
     output["threads"]["server"]["lastupdate"]) = \
        app.server.get_status()
    output["threads"]["server"]["lastupdate"] = \
        abs(time.time() - float(output["threads"]["server"]["lastupdate"]))

    return output


@post_route("speed")
def speed(jdata, app):
    with app.download_limiter_lock:
        down = app.download_limiter.get_rate()
    with app.upload_limiter_lock:
        up = app.upload_limiter.get_rate()
    return [up, down]


@post_route("downloadqadd")
def download_q_add(jdata, app):
    if isinstance(jdata[u"data"], dict):
        try:
            peer_uuid = jdata[u"data"][u"uuid"]
            sharedir = jdata[u"data"][u"sharedir"]
            filename = jdata[u"data"][u"filename"]
            filesize = int(jdata[u"data"][u"filesize"])
            filemod = float(jdata[u"data"][u"filemodtime"])
        except:
            return -1

        with app.download_q_lock:
            logging.debug("Adding File to Download Q:" + str(
                (peer_uuid, sharedir, filename, filesize, filemod)))
            if not peer_uuid in app.download_q:
                app.download_q[peer_uuid] = []
            if (sharedir, filename, filesize, filemod) \
                    not in app.download_q[peer_uuid]:
                app.download_q[peer_uuid].append(
                    (sharedir, filename, filesize, filemod))
                return 1
            return 2


@post_route("downloadqremove")
def download_q_remove(jdata, app):
    data = jdata[u"data"]
    if isinstance(data, dict):
        try:
            peer_uuid = data[u"uuid"]
            sharedir = data[u"sharedir"]
            filename = data[u"filename"]
            filesize = int(data[u"filesize"])
            filemod = float(data[u"filemodtime"])
        except:
            return -1

        with app.download_q_lock:
            logging.debug("Removing File to Download Q:" + str(
                (peer_uuid, sharedir, filename, filesize, filemod)))
            if peer_uuid in app.download_q:
                # logging.debug(str(((sharedir,filename,filesize,filemod))))
                # logging.debug(str(app.download_q[peer_uuid]))
                while (sharedir, filename, filesize, filemod) \
                        in app.download_q[peer_uuid]:
                    app.download_q[peer_uuid].remove(
                        (sharedir, filename, filesize, filemod))
                # if len(app.download_q[peer_uuid]) == 0: del app.download_q[peer_uuid]
                return 1
            return 2


@post_route("downloadqmove")
def download_q_move(jdata, app):
    data = jdata[u"data"]
    if isinstance(data, dict):
        try:
            peer_uuid = data[u"uuid"]
            sharedir = data[u"sharedir"]
            filename = data[u"filename"]
            filesize = int(data[u"filesize"])
            filemod = float(data[u"filemodtime"])
            newloc = int(data[u"newloc"])
        except Exception:
            return -1
    else:
        return -1

    with app.download_q_lock:
        logger.debug(
            "Moving File in Download Q: " + str((
                peer_uuid, sharedir, filename, filesize, filemod, newloc)))
        if peer_uuid in app.download_q:
            while (sharedir, filename, filesize, filemod) \
                    in app.download_q[peer_uuid]:
                app.download_q[peer_uuid].remove(
                    (sharedir, filename, filesize, filemod))
            app.download_q[peer_uuid].insert(
                min(newloc, len(app.download_q[peer_uuid])),
                ((sharedir, filename, filesize, filemod)))
            return 1
        return 2


@post_route("downloadqget")
def download_q_get(jdata, app):
    with app.settings_lock:
        local_copy_download_directory = os.path.normpath(app.settings["Download Location"])
        with app.download_q_lock:
            peerinfo = {}
            fileinfo = defaultdict(dict)
            for peer_uuid in app.settings["Peers"]:
                try:
                    peerinfo[peer_uuid] = [
                        app.settings["Peers"][peer_uuid]["nickname"],
                        app.settings["Peers"][peer_uuid]["localnick"]]
                except:
                    peerinfo[peer_uuid] = [u"Unknown Nickname", u""]
            for peer_uuid in app.download_q:
                for (sharedir, filename, filesize, modtime) \
                        in app.download_q[peer_uuid]:
                    filename_incomplete = os.path.normpath(os.path.join(
                        local_copy_download_directory,
                        filename + FILESYSTEM_WORKINPROGRESS_SUFFIX))
                    try:
                        current_size = os.path.getsize(filename_incomplete)
                    except:
                        current_size = 0
                    fileinfo[peer_uuid][filename] = current_size
            output = {
                "result": app.download_q,
                "peerinfo": peerinfo,
                "fileinfo": fileinfo
            }
    return output


@post_route("completedqclear")
def completed_q_clear(jdata, app):
    with app.completed_q_lock:
        app.completed_q = []
    return 1


@post_route("completedqget")
def completed_q_get(jdata, app):
    with app.settings_lock:
        with app.completed_q_lock:
            peerinfo = {}
            for peer_uuid in app.settings["Peers"].keys():
                try:
                    peerinfo[peer_uuid] = [
                        app.settings["Peers"][peer_uuid]["nickname"],
                        app.settings["Peers"][peer_uuid]["localnick"]]
                except:
                    peerinfo[peer_uuid] = [u"Unknown Nickname", u""]
            output = {"result": app.completed_q[::-1], "peerinfo": peerinfo}
    return output


@post_route("uploadqget")
def upload_q_get(jdata, app):
    raise NotImplementedError


@post_route("browseresult")
def browse_result(jdata, app):
    """
    Request to retrieve a result previously asked wit browse()

    """
    while True:
        try:
            peer_uuid = jdata["data"]['uuid']
            share_dir = jdata["data"]['sharedir']
        except (KeyError, TypeError):
            message = "required field missing in request"
            break

        try:
            with app.share_listings_lock:
                return {
                    "result": app.share_listings[(peer_uuid, share_dir)][1]
                }
        except KeyError:
            message = "no such request"
            break

    logger.error("browse-result request failed (%s)", message)
    return {
        "result": API_ERROR,
        "message": message
    }


@post_route("browse")
def browse(jdata, app):
    """
    A request to get a directory listing from a peer.

    The directory tree is not cached on local peer. Instead, a request is
    posted to appropriate peer and the caller gets a result handler.
    """
    while True:
        try:
            peer_uuid = jdata["data"]['uuid']
            share_dir = jdata["data"]['sharedir']
        except (KeyError, TypeError):
            message = "required field missing in request"
            break

        if peer_uuid not in app.settings["Peers"]:
            message = "unknown peer"
            break

        browse_result_uuid = uuid.uuid4().hex
        logger.debug(
            "getting directory listing from %r for share %s with result %r",
            peer_uuid, share_dir, browse_result_uuid)

        # We request to this peer to give us the data.
        request = TacoApp.instance.commands.request_share_listing_cmd(
            peer_uuid, share_dir, browse_result_uuid)
        TacoApp.instance.add_to_output_queue(
            peer_uuid, request, PRIORITY_MEDIUM)

        return {
            "sharedir": share_dir,
            "result": browse_result_uuid
        }

    logger.error("browse request failed (%s)", message)
    return {
        "result": API_ERROR,
        "message": message
    }


@post_route("peerstatus")
def peer_status(jdata, app):

    output = {}
    with app.settings_lock:
        for peer_uuid in app.settings["Peers"].keys():
            if app.settings["Peers"][peer_uuid]["enabled"]:
                incoming = app.server.get_client_last_request(peer_uuid)
                outgoing = app.clients.get_client_last_reply(peer_uuid)
                timediffinc = abs(time.time() - incoming)
                timediffout = abs(time.time() - outgoing)
                try:
                    nickname_status = app.settings["Peers"][peer_uuid]["nickname"]
                except:
                    nickname_status = "Unknown"
                output[peer_uuid] = [
                    incoming, outgoing, timediffinc, timediffout, nickname_status,
                    app.settings["Peers"][peer_uuid]["localnick"]]
    return output


@post_route("settingssave")
def settings_save(jdata, app):
    data = jdata[u"data"]
    if isinstance(data, list):
        if len(data) >= 0:
            with app.settings_lock:
                logger.info("API Access: SETTINGS -- Action: SAVE")
                for (key_name, value) in data:
                    app.settings[key_name] = value
                app.store.save(False)
                return 1
    return -1


@post_route("sharesave")
def share_save(jdata, app):
    data = jdata[u"data"]
    if isinstance(data, list):
        if len(data) >= 0:
            with app.settings_lock:
                logger.info("API Access: SHARE -- Action: SAVE")
                app.settings["Shares"] = []
                for (sharename, sharelocation) in data:
                    app.settings["Shares"].append([sharename, sharelocation])
                app.store.save(False)
                return 1
    return -1


@post_route("getchat")
def get_chat(jdata, app):
    output_chat = []
    with app.settings_lock:
        localuuid = app.settings["Local UUID"]
        with app.chat_log_lock:
            for [puuid, thetime, msg] in app.chat_log:
                if puuid in app.settings["Peers"] and \
                        "nickname" in app.settings["Peers"][puuid]:
                    nickname = app.settings["Peers"][puuid]["nickname"]
                elif app.settings["Local UUID"] == puuid:
                    nickname = app.settings["Nickname"]
                else:
                    nickname = puuid
                if puuid == localuuid:
                    output_chat.append([0, nickname, puuid, thetime, msg])
                else:
                    output_chat.append([1, nickname, puuid, thetime, msg])
    return output_chat


@post_route("sendchat")
def send_chat(jdata, app):
    data = jdata[u"data"]
    if isinstance(data, str) or isinstance(data, unicode):
        if len(data) > 0:
            TacoApp.instance.commands.request_chat_cmd(data)
            return 1
    return -1


@post_route("chatuuid")
def chat_uuid(jdata, app):
    with app.chat_uuid_lock:
        return [app.chat_uuid]


@post_route("peersave")
def peer_save(jdata, app):
    data = jdata[u"data"]
    if isinstance(data, list):
        if len(data) >= 0:
            with app.settings_lock:
                logger.info("API Access: PEER -- Action: SAVE")
                app.settings["Peers"] = {}
                for (hostname, port, local_nick, peer_uuid, client_pub,
                     server_pub, dynamic, enabled) in data:
                    app.settings["Peers"][str(peer_uuid)] = {
                        "hostname": hostname, "port": int(port),
                        "localnick": local_nick,
                        "dynamic": int(dynamic),
                        "enabled": int(enabled),
                        "clientkey": client_pub,
                        "serverkey": server_pub
                    }
                app.store.save(need_lock=False, load_after=True)
            app.restart()
            return 1
    return -1
