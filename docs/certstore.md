Certificate Store
=================

Structure
---------

### public directory

This is where files with .key extension store only public keys
to be used with peers. For each peer there is a *peerid*-client.key
file used with the DEALER socket (see TacoClients) 
and a *peerid*-server.key used with REP socket (see TacoServer).

The persistent source for these keys is in [Settings](#settings)
(see below), with keys in the store being created and deleted by 
[TacoSettings](#tacosettings) based on enabled/disabled status of 
each peer.

It is worth noting that the settings are dumped to disk on each
peer save.

The authenticator for clients will point its `configure_curve()`
to this directory, so incoming connections to DEALER socket will
search incoming keys here.

### private directory

This is where the key for local peer are stored. The folder contains
two pairs of public-private keys used for socket according to
(zmq_curve)[http://api.zeromq.org/4-1:zmq-curve]:
- one for the clients that is set on the DEALER socket as the
client's key in ZMQ_CURVE_PUBLICKEY and ZMQ_CURVE_SECRETKEY 
- one for the server that is set on the REP socket as the
server's key in ZMQ_CURVE_PUBLICKEY and ZMQ_CURVE_SECRETKEY 

Public keys are cached in TacoApp's `public_keys` member and
are exposed in settings page.

The authenticator for server will point its `configure_curve()`
to this directory, so incoming connections to REP socker will
search incoming keys here.


Settings
--------

The program uses a settings .json file that has some fields
related to the certificate store:

### TacoNET Certificates Store

Root directory for our certificates. 
This is used in two ways:
- as a place where one directory per local uuid is stored;
- as a temporary directory for creating the new certificates.

Most of the code uses this value to create paths for 
public and private directories.

### Local UUID

This is a unique identifier for a running instance.
If the value is not found in loaded settings then a new, unique value
is generated here and assigned.
A directory with this name will be created in certstore, allowing
"namespaces" where different sets of keys are stored in a single place.
Messages (requests or replies) originating from this instance will
have this value in `NET_IDENT` field.
The value is used to uniquely identify peers among themselves and
is part of the chat log structure.

### Peers

The Peers key stores a dictionary, with keys being peer uuids and
values holding a dictionary. Of interest in this context are
clientkey and serverkey.

TacoSettings
------------

The class that handles settings in code is TacoSettings. The json that
it load represents the central storage space for keys. Based on 
enabled/diabled state of each peer the keys in the file system
certificate store, public directory, are created or deleted.




