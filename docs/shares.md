Sharing Files
-------------

Users can share parts of their file system. Each such share
corresponds to a directory on the host machine and other peers
can inspect its content.

In the program we use paths to represent files and directories inside
these shares where first element is always the name of the share
followed by 0 or more directories and an optional file. Individual
parts are always separated by a `/` character (yes, on Windows, too).

Exploring
=========

### API

The api provides two endpoints for exploring shares:
- browse starts the process of retrieving the information so that it is
available to the api provider
- browseresult retrieves the ersult once it is available.

### Client

The communication between the peer that is interested in the share listing
and the peer that's asking is also split into two parts:
- issuing the command with a NET_REQUEST_SHARE_LISTING and
- retrieving the result with a NET_REQUEST_SHARE_LISTING_RESULTS.

### File System

A peer that receives a browse request through NET_REQUEST_SHARE_LISTING
will add it to the file system queue
