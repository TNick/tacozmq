import taco.globals
import taco.constants
import taco.defaults
import os
import json
import logging
import time


def Load_Settings(needlock=True):
    logging.debug("loading settings ...")
    save_after = False
    if needlock:
        taco.globals.settings_lock.acquire()

    try:
        try:
            logging.debug("Loading Settings JSON")
            with open(taco.constants.JSON_SETTINGS_FILENAME, 'r') as fin:
                taco.globals.settings = json.load(fin)
        except Exception:
            taco.globals.settings = {"Peers": {}, "Shares": []}

        logging.debug("Verifying the settings loaded from the json "
                      "isn't missing any required keys")
        for keyname in taco.defaults.default_settings_kv.keys():
            if not keyname in taco.globals.settings:
                taco.globals.settings[keyname] = \
                    taco.defaults.default_settings_kv[keyname]
                save_after = True

        if not os.path.isdir(taco.globals.settings["TacoNET Certificates Store"]):
            logging.debug("Making %s Certificates Store",
                          taco.constants.APP_NAME)
            os.makedirs(taco.globals.settings["TacoNET Certificates Store"])

        logging.debug("Verifying settings share list is in correct format")
        if not isinstance(taco.globals.settings["Shares"], list):
            taco.globals.shares = []
            save_after = True

        logging.debug("Verifying settings peer dict is in correct format")
        keep_keys = []
        for peer_uuid in taco.globals.settings["Peers"].keys():
            peer_data = taco.globals.settings["Peers"][peer_uuid]
            if peer_data["enabled"]:
                Enable_Key(peer_uuid, "client", peer_data["clientkey"], False)
                Enable_Key(peer_uuid, "server", peer_data["serverkey"], False)
                keep_keys.append(peer_uuid + "-client.key")
                keep_keys.append(peer_uuid + "-server.key")
        Disable_Keys(keep_keys, False)

    finally:
        if needlock:
            taco.globals.settings_lock.release()

    logging.debug("settings loaded")
    if save_after:
        Save_Settings()


def Save_Settings(needlock=True):
    logging.debug("saving settings...")
    if needlock:
        taco.globals.settings_lock.acquire()
    try:
        with open(taco.constants.JSON_SETTINGS_FILENAME, 'w') as fout:
            json.dump(fout, taco.globals.settings, indent=4, sort_keys=True)
    finally:
        if needlock:
            taco.globals.settings_lock.release()
    logging.debug("settings saved")
    Load_Settings(needlock)


def Disable_Keys(keys_to_keep, needlock=True):
    logging.debug("Disabling Peer Keys if Needed")
    if needlock:
        taco.globals.settings_lock.acquire()
    try:
        public_dir = os.path.normpath(os.path.abspath(os.path.join(
            taco.globals.settings["TacoNET Certificates Store"],
            taco.globals.settings["Local UUID"],
            "public"))
        )
    finally:
        if needlock:
            taco.globals.settings_lock.release()

    if not os.path.exists(public_dir):
        os.makedirs(public_dir)
    filelisting = os.listdir(os.path.normpath(os.path.abspath(public_dir)))
    delete_files = []
    logging.debug("Keys that will be kept: " + str(keys_to_keep))
    for filename in filelisting:
        if filename not in keys_to_keep:
            delete_files.append(filename)

    for file_to_delete in delete_files:
        logging.info("Deleting key: " + file_to_delete)
        full_path = os.path.normpath(os.path.abspath(os.path.join(
            public_dir, file_to_delete)))
        if os.path.isfile(full_path):
            os.remove(full_path)


def Enable_Key(peer_uuid, key_type, key_string, needlock):
    logging.info("Enabling KEY for UUID:%s -- %s -- %s",
                 peer_uuid, key_type, key_string)
    template = """
#   **** Saved on %s by tacozmq  ****
#   for peer: %s
#   type: %s
#   ZeroMQ CURVE Public Certificate
#   Exchange securely, or use a secure mechanism to verify the contents
#   of this file after exchange. Store public certificates in your home
#   directory, in the .curve subdirectory.

metadata
curve
    public-key = "%s"
  """

    if needlock:
        taco.globals.settings_lock.acquire()
    public_dir = os.path.normpath(os.path.abspath(os.path.join(
        taco.globals.settings["TacoNET Certificates Store"],
        taco.globals.settings["Local UUID"],
        "public")))
    if needlock:
        taco.globals.settings_lock.release()
    location = os.path.normpath(os.path.abspath(os.path.join(
        public_dir, '%s-%s.key' % (peer_uuid, key_type))))

    template_out = template % (
        str(time.time()), peer_uuid, key_type, key_string)
    if not os.path.isdir(public_dir):
        os.makedirs(public_dir)
    with open(location, 'w') as fout:
        fout.write(template_out)
