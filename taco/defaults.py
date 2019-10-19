# -*- coding: utf-8 -*-
"""
Application-level defaults.
"""
from __future__ import unicode_literals

import uuid
import taco.constants
import sys

if sys.version_info > (3, 0):
    unicode = str

default_settings_kv = {
    "Download Location": "downloads/",
    "Nickname": "Your Nickname Here",
    "Application Port": 5440,
    "Application IP": "0.0.0.0",
    "Web Port": 5340,
    "Web IP": "127.0.0.1",
    "Download Limit": 50,
    "Upload Limit": 50,

    # This is a unique identifier for a running instance.
    # If the value is not found in loaded settings then a new, unique value
    # is generated here and assigned.
    # A directory with this name will be created in certstore, allowing
    # "namespaces" where different sets of keys are stored in a single place.
    # Messages (requests or replies) originating from this instance will
    # have this value in NET_IDENT field.
    # The value is used to uniquely identify peers among themselves and
    # is part of the chat log structure.
    "Local UUID": unicode(uuid.uuid4().hex),

    # Root directory for our certificates. This is used in two ways:
    # - as a place where one directory per local uuid is stored;
    # - as a temporary directory for creating the new certificates.
    # Most of the code uses this value to create paths for public and private
    # directories.
    "TacoNET Certificates Store": "certstore/",

    # The list of shared resources.
    "Shares": {},

    # The list of peers we know about.
    "Peers": {}
}

default_peers_kv = {
    "enabled": False,
    "hostname": "127.0.0.1",
    "port": "9001",
    "localnick": "Local Nickname",
    "dynamic": False,
    "clientkey": "",
    "serverkey": ""
}
