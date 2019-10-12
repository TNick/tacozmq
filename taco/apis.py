# -*- coding: utf-8 -*-
"""
/api.post receives a json string that gets converted to a dict.
All such calls are required to have an action parameter.
For each action this module needs to define a function
wrapped by @post_route("action"). These handlers get collected in
`post_routes` which is then used in routes.py to handle the call.
"""
import taco.settings
import taco.server
import taco.clients
import taco.globals
import taco.constants
import taco.filesystem
import taco.commands
import time
import os
import uuid
import logging
import json
import sys
from collections import defaultdict

if sys.version_info > (3, 0):
    unicode = str

# This is where we collect all paths.
post_routes = {}


def post_route(action):
    """ Wrapper we use to collect all paths in a single dict. """
    def wrap(f):
        def wrapped_f(*args, **kwargs):
            result = f(*args, **kwargs)
            if result is None:
                result = "-1"
            elif isinstance(result, int):
                result = str(result)
            elif not isinstance(result, str):
                result = json.dumps(result)
            logging.log(logging.DEBUG - 1, "Result for %s is: %s", action, result)
            return result

        post_routes[action] = wrapped_f
        return wrapped_f

    return wrap


@post_route("apistatus")
def api_status(jdata):
    return {"status": 1}


@post_route("threadstatus")
def thread_status(jdata):
    output = {"threads": {}}
    output["threads"]["clients"] = {}
    output["threads"]["server"] = {}

    output["threads"]["clients"]["alive"] = taco.globals.clients.is_alive()
    (output["threads"]["clients"]["status"],
     output["threads"]["clients"]["lastupdate"]) = \
        taco.globals.clients.get_status()
    output["threads"]["clients"]["lastupdate"] = abs(
        time.time() - float(output["threads"]["clients"]["lastupdate"]))

    output["threads"]["server"]["alive"] = taco.globals.server.is_alive()
    (output["threads"]["server"]["status"],
     output["threads"]["server"]["lastupdate"]) = \
        taco.globals.server.get_status()
    output["threads"]["server"]["lastupdate"] = \
        abs(time.time() - float(output["threads"]["server"]["lastupdate"]))

    return output


@post_route("speed")
def speed(jdata):
    with taco.globals.download_limiter_lock:
        down = taco.globals.download_limiter.get_rate()
    with taco.globals.upload_limiter_lock:
        up = taco.globals.upload_limiter.get_rate()
    return [up, down]


@post_route("downloadqadd")
def download_q_add(jdata):
    if isinstance(jdata[u"data"], dict):
        try:
            peer_uuid = jdata[u"data"][u"uuid"]
            sharedir = jdata[u"data"][u"sharedir"]
            filename = jdata[u"data"][u"filename"]
            filesize = int(jdata[u"data"][u"filesize"])
            filemod = float(jdata[u"data"][u"filemodtime"])
        except:
            return -1

        with taco.globals.download_q_lock:
            logging.debug("Adding File to Download Q:" + str(
                (peer_uuid, sharedir, filename, filesize, filemod)))
            if not peer_uuid in taco.globals.download_q:
                taco.globals.download_q[peer_uuid] = []
            if (sharedir, filename, filesize, filemod) \
                    not in taco.globals.download_q[peer_uuid]:
                taco.globals.download_q[peer_uuid].append(
                    (sharedir, filename, filesize, filemod))
                return 1
            return 2


@post_route("downloadqremove")
def download_q_remove(jdata):
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

        with taco.globals.download_q_lock:
            logging.debug("Removing File to Download Q:" + str(
                (peer_uuid, sharedir, filename, filesize, filemod)))
            if peer_uuid in taco.globals.download_q:
                # logging.debug(str(((sharedir,filename,filesize,filemod))))
                # logging.debug(str(taco.globals.download_q[peer_uuid]))
                while (sharedir, filename, filesize, filemod) \
                        in taco.globals.download_q[peer_uuid]:
                    taco.globals.download_q[peer_uuid].remove(
                        (sharedir, filename, filesize, filemod))
                # if len(taco.globals.download_q[peer_uuid]) == 0: del taco.globals.download_q[peer_uuid]
                return 1
            return 2


@post_route("downloadqmove")
def download_q_move(jdata):
    data = jdata[u"data"]
    if isinstance(data, dict):
        try:
            peer_uuid = data[u"uuid"]
            sharedir = data[u"sharedir"]
            filename = data[u"filename"]
            filesize = int(data[u"filesize"])
            filemod = float(data[u"filemodtime"])
            newloc = int(data[u"newloc"])
        except:
            return -1
    with taco.globals.download_q_lock:
        logging.debug(
            "Moving File in Download Q:" + str((
                peer_uuid, sharedir, filename, filesize, filemod, newloc)))
        if peer_uuid in taco.globals.download_q:
            while (sharedir, filename, filesize, filemod) \
                    in taco.globals.download_q[peer_uuid]:
                taco.globals.download_q[peer_uuid].remove(
                    (sharedir, filename, filesize, filemod))
            taco.globals.download_q[peer_uuid].insert(
                min(newloc, len(taco.globals.download_q[peer_uuid])),
                ((sharedir, filename, filesize, filemod)))
            return 1
        return 2


@post_route("downloadqget")
def download_q_get(jdata):
    with taco.globals.settings_lock:
        local_copy_download_directory = os.path.normpath(taco.globals.settings["Download Location"])
        with taco.globals.download_q_lock:
            peerinfo = {}
            fileinfo = defaultdict(dict)
            for peer_uuid in taco.globals.settings["Peers"]:
                try:
                    peerinfo[peer_uuid] = [
                        taco.globals.settings["Peers"][peer_uuid]["nickname"],
                        taco.globals.settings["Peers"][peer_uuid]["localnick"]]
                except:
                    peerinfo[peer_uuid] = [u"Unknown Nickname", u""]
            for peer_uuid in taco.globals.download_q:
                for (sharedir, filename, filesize, modtime) \
                        in taco.globals.download_q[peer_uuid]:
                    filename_incomplete = os.path.normpath(os.path.join(
                        local_copy_download_directory,
                        filename + taco.constants.FILESYSTEM_WORKINPROGRESS_SUFFIX))
                    try:
                        current_size = os.path.getsize(filename_incomplete)
                    except:
                        current_size = 0
                    fileinfo[peer_uuid][filename] = current_size
            output = {
                "result": taco.globals.download_q,
                "peerinfo": peerinfo,
                "fileinfo": fileinfo
            }
    return output


@post_route("completedqclear")
def completed_q_clear(jdata):
    with taco.globals.completed_q_lock:
        taco.globals.completed_q = []
    return 1


@post_route("completedqget")
def completed_q_get(jdata):
    with taco.globals.settings_lock:
        with taco.globals.completed_q_lock:
            peerinfo = {}
            for peer_uuid in taco.globals.settings["Peers"].keys():
                try:
                    peerinfo[peer_uuid] = [
                        taco.globals.settings["Peers"][peer_uuid]["nickname"],
                        taco.globals.settings["Peers"][peer_uuid]["localnick"]]
                except:
                    peerinfo[peer_uuid] = [u"Unknown Nickname", u""]
            output = {"result": taco.globals.completed_q[::-1], "peerinfo": peerinfo}
    return output


@post_route("uploadqget")
def upload_q_get(jdata):
    raise NotImplementedError


@post_route("browseresult")
def browse_result(jdata):
    output = {}
    data = jdata[u"data"]
    if isinstance(data, dict):
        if u"sharedir" in data and u"uuid" in data:
            with taco.globals.share_listings_lock:
                if (data[u"uuid"], data[u"sharedir"]) \
                        in taco.globals.share_listings:
                    output = {
                        "result": taco.globals.share_listings[(
                            data[u"uuid"],
                            data[u"sharedir"])][1]}
    return output


@post_route("browse")
def browse(jdata):
    data = jdata[u"data"]
    if isinstance(data, dict):
        if u"uuid" in data and u"sharedir" in data:
            peer_uuid = data[u"uuid"]
            sharedir = data[u"sharedir"]
            browse_result_uuid = uuid.uuid4().hex
            logging.critical(
                "Getting Directory Listing from: %s for share: %s",
                peer_uuid, sharedir)
            request = taco.commands.Request_Share_Listing(
                peer_uuid, sharedir, browse_result_uuid)
            taco.globals.Add_To_Output_Queue(peer_uuid, request, 2)
            return {
                "sharedir": sharedir,
                "result": browse_result_uuid
            }


@post_route("peerstatus")
def peer_status(jdata):
    output = {}
    with taco.globals.settings_lock:
        for peer_uuid in taco.globals.settings["Peers"].keys():
            if taco.globals.settings["Peers"][peer_uuid]["enabled"]:
                incoming = taco.globals.server.get_client_last_request(peer_uuid)
                outgoing = taco.globals.clients.get_client_last_reply(peer_uuid)
                timediffinc = abs(time.time() - incoming)
                timediffout = abs(time.time() - outgoing)
                nickname_status = "Unknown"
                try:
                    nickname_status = taco.globals.settings["Peers"][peer_uuid]["nickname"]
                except:
                    nickname_status = "Unknown"
                output[peer_uuid] = [
                    incoming, outgoing, timediffinc, timediffout, nickname_status,
                    taco.globals.settings["Peers"][peer_uuid]["localnick"]]
    return output


@post_route("settingssave")
def settings_save(jdata):
    data = jdata[u"data"]
    if isinstance(data, list):
        if len(data) >= 0:
            with taco.globals.settings_lock:
                logging.info("API Access: SETTINGS -- Action: SAVE")
                for (keyname, value) in data:
                    taco.globals.settings[keyname] = value
                taco.settings.Save_Settings(False)
                return 1


@post_route("sharesave")
def share_save(jdata):
    data = jdata[u"data"]
    if isinstance(data, list):
        if len(data) >= 0:
            with taco.globals.settings_lock:
                logging.info("API Access: SHARE -- Action: SAVE")
                taco.globals.settings["Shares"] = []
                for (sharename, sharelocation) in data:
                    taco.globals.settings["Shares"].append([sharename, sharelocation])
                taco.settings.Save_Settings(False)
                return 1


@post_route("getchat")
def get_chat(jdata):
    output_chat = []
    with taco.globals.settings_lock:
        localuuid = taco.globals.settings["Local UUID"]
        with taco.globals.chat_log_lock:
            for [puuid, thetime, msg] in taco.globals.chat_log:
                if puuid in taco.globals.settings["Peers"] and \
                        "nickname" in taco.globals.settings["Peers"][puuid]:
                    nickname = taco.globals.settings["Peers"][puuid]["nickname"]
                elif taco.globals.settings["Local UUID"] == puuid:
                    nickname = taco.globals.settings["Nickname"]
                else:
                    nickname = puuid
                if puuid == localuuid:
                    output_chat.append([0, nickname, puuid, thetime, msg])
                else:
                    output_chat.append([1, nickname, puuid, thetime, msg])
    return output_chat


@post_route("sendchat")
def send_chat(jdata):
    data = jdata[u"data"]
    if isinstance(data, str) or isinstance(data, unicode):
        if len(data) > 0:
            taco.commands.Request_Chat(data)
            return 1


@post_route("chatuuid")
def chat_uuid(jdata):
    with taco.globals.chat_uuid_lock:
        return [taco.globals.chat_uuid]


@post_route("peersave")
def peer_save(jdata):
    data = jdata[u"data"]
    if isinstance(data, list):
        if len(data) >= 0:
            with taco.globals.settings_lock:
                logging.info("API Access: PEER -- Action: SAVE")
                taco.globals.settings["Peers"] = {}
                for (hostname, port, localnick, peeruuid, clientpub,
                     serverpub, dynamic, enabled) in data:
                    taco.globals.settings["Peers"][str(peeruuid)] = {
                        "hostname": hostname, "port": int(port),
                        "localnick": localnick,
                        "dynamic": int(dynamic),
                        "enabled": int(enabled),
                        "clientkey": clientpub,
                        "serverkey": serverpub
                    }
                taco.settings.Save_Settings(False)

            taco.globals.server.stop.set()
            taco.globals.clients.stop.set()
            taco.globals.server.join()
            taco.globals.clients.join()
            taco.globals.server = taco.server.TacoServer()
            taco.globals.clients = taco.clients.TacoClients()
            taco.globals.server.start()
            taco.globals.clients.start()
            return 1
