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
    "Local UUID": unicode(uuid.uuid4().hex),
    "TacoNET Certificates Store": "certstore/"
}

default_peers_kv = {
    "enabled": False,
    "hostname": "127.0.0.1",
    "port": "9001",
    "localnick": "Local Nickname",
    "dynamic": False,
    "clientkey": "", "serverkey": ""
}
