# -*- coding: utf-8 -*-
"""
Package-wide constants.
"""
from __future__ import unicode_literals
from socket import gethostname
import re

APP_CODE_NAME = "Dirt Diver"
# Cool Breeze,Betty Blue, Hammerhead, Dirt Diver, Whiplash, Whipporwill,Dog Patch 06,Red Cap
APP_NAME = "TacoZMQ"
APP_TAGLINE = [
    "It's blue and orange because I am a hack. --Scott",
    "Save it for beta. --Scott",
    "Laddergoatdotcom.com --Scott",
    "You're going to say THAT about Swifty? To ME of all people? "
    "AND WITH THAT TONE? --Scott",
    "Forget the search feature. Why would we spend time developing "
    "something nobody will use? --Scott",
    "No is an acceptable answer. --Scott"]

APP_VERSION = 0.3
APP_STAGE = "Beta"
APP_AUTHOR = ["Scott Powers", "Nicu Tofan"]

KB = 2 ** 10
MB = 2 ** 20
GB = 2 ** 30
TB = 2 ** 40
MAX_NICKNAME_LENGTH = 48
MAX_CHAT_MESSAGE_LENGTH = 512
CHAT_LOG_MAXSIZE = 128

HOSTNAME = gethostname()
CHUNK_SIZE = 1024 * 16

JSON_SETTINGS_FILENAME = "settings.json"
CERT_STORE_DIR = "certstore/"

KEY_GENERATION_PREFIX = "taconet"  # needs to be changed later
KEY_CLIENT_SECRET_SUFFIX = "client.key_secret"
KEY_SERVER_SECRET_SUFFIX = "server.key_secret"
KEY_CLIENT_PUBLIC_SUFFIX = "client.key"
KEY_SERVER_PUBLIC_SUFFIX = "server.key"


LOOP_TOKEN_COUNT = 250

# Minimum time to wait before attempting a reconnect [seconds]
CLIENT_RECONNECT_MIN = 0

# Time to add between consecutive failed reconnects [seconds]
# - first attempt will be at t+CLIENT_RECONNECT_MIN
# - second attempt will be at t+CLIENT_RECONNECT_MIN+CLIENT_RECONNECT_MOD
# - and so on until we reach CLIENT_RECONNECT_MAX
CLIENT_RECONNECT_MOD = 2

# Maximum time to wait before attempting a reconnect [seconds]
CLIENT_RECONNECT_MAX = 16

FILESYSTEM_CACHE_TIMEOUT = 120
FILESYSTEM_LISTING_TIMEOUT = 300
FILESYSTEM_CACHE_PURGE = 30
FILESYSTEM_WORKER_COUNT = 4
FILESYSTEM_RESULTS_SIZE = 16
FILESYSTEM_CHUNK_SIZE = KB * 128
FILESYSTEM_CREDIT_MAX = 35
FILESYSTEM_WORKINPROGRESS_SUFFIX = ".filepart"

DOWNLOAD_Q_CHECK_TIME = 2
DOWNLOAD_Q_WAIT_FOR_ACK = 30
DOWNLOAD_Q_WAIT_FOR_DATA = 300

# When a hartbeat needs to be scheduled the interval is randomly
# picked from this interval.
ROLLCALL_MIN = 2
ROLLCALL_MAX = 5

# The time our peers have to send a hartbeat or other communication.
# If expires we consider the peer to be timed out. [seconds]
ROLLCALL_TIMEOUT = ROLLCALL_MAX * 2

NET_GARBAGE = "G"
NET_IDENT = "I"

NET_REQUEST = "r"
NET_REPLY = "R"
NET_DATABLOCK = "D"

NET_REQUEST_ROLLCALL = "a"
NET_REPLY_ROLLCALL = "A"

NET_REQUEST_CERTS = "b"
NET_REPLY_CERTS = "B"

NET_REQUEST_CHAT = "c"
NET_REPLY_CHAT = "C"

NET_REQUEST_SHARE_LISTING = "d"
NET_REPLY_SHARE_LISTING = "D"

NET_REQUEST_SHARE_LISTING_RESULTS = "e"
NET_REPLY_SHARE_LISTING_RESULTS = "E"

NET_REQUEST_START_DOWNLOAD = "f"
NET_REPLY_START_DOWNLOAD = "F"


NET_REQUEST_GET_FILE_CHUNK = "x"
NET_REPLY_GET_FILE_CHUNK = "X"

NET_REQUEST_GIVE_FILE_CHUNK = "z"
NET_REPLY_GIVE_FILE_CHUNK = "Z"

RE_UUID_CHECKER = "([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-f0-9]{32})"
RE_NICKNAME_CHECKER = "^[\w\.\-\(\) ]{3," + str(MAX_NICKNAME_LENGTH) + "}$"
RE_PORT_CHECKER = "^0*(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{1,3}|[0-9])$"
RE_HOST_CHECKER = "^(?:(?:(?:(?:[a-zA-Z0-9][-a-zA-Z0-9]{0,61})?[a-zA-Z0-9])[.])*(?:[a-zA-Z][-a-zA-Z0-9]{0,61}[a-zA-Z0-9]|[a-zA-Z])[.]?)$"
RE_CHAT_CHECKER = "^[!-~ ]{1," + str(MAX_CHAT_MESSAGE_LENGTH) + "}$"
RE_IP_CHECKER = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"

UUID_CHECKER = re.compile(RE_UUID_CHECKER, re.UNICODE)
NICKNAME_CHECKER = re.compile(RE_NICKNAME_CHECKER, re.UNICODE)
CHAT_CHECKER = re.compile(RE_CHAT_CHECKER, re.UNICODE)
SHARE_NAME_CHECKER = re.compile("^\w[\w \-\.]{1,126}\w$", re.UNICODE)
DIR_NAME_CHECKER = re.compile("^\w[\w \-\.]{1,126}\w$", re.UNICODE)

# The most verbose level for logging.
TRACE = 1

# Indicates there is no identity in a result that usually returns an identity
NO_IDENTITY = "0"

# The value returned in result by json when an error condition was encountered.
API_ERROR = "ERROR"
# The value returned in result by json when the request succeded and there's
# nothing else to return.
API_OK = "OK"

# Highest priority message.
# TODO: this is not really used in code or any faster.
PRIORITY_HIGH = 1
# Common priority message.
PRIORITY_MEDIUM = 2
# Low priority message.
PRIORITY_LOW = 3
# A file transfer.
PRIORITY_FILE = 4

# The transfer is in an initial state.
TRANSFER_INIT = 0
# The transfer has been acknowledged by the other party
# and will start as soon as possible.
TRANSFER_ACK = 1
# The transfer is in progress.
TRANSFER_IN_PROGRESS = 2
# The transfer could not be completed.
TRANSFER_FAILED = -2
# The transfer could not be completed.
TRANSFER_COMPLETED = 3
