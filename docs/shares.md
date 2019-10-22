Sharing Files
=============

Users can share parts of their file system. Each such share
corresponds to a directory on the host machine and other peers
can inspect its content.

In the program we use paths to represent files and directories inside
these shares where first element is always the name of the share
followed by 0 or more directories and an optional file. Individual
parts are always separated by a `/` character (yes, on Windows, too).

Exploring
---------

### API

The api provides two endpoints for exploring shares:
- browse starts the process of retrieving the information so that it is
available to the api provider
- browseresult retrieves the result once it is available.

### Client

The communication between the peer that is interested in the share listing
and the peer that's asking is also split into two parts:
- issuing the command with a NET_REQUEST_SHARE_LISTING and
- retrieving the result with a NET_REQUEST_SHARE_LISTING_RESULTS.

### File System

A peer that receives a browse request through NET_REQUEST_SHARE_LISTING
will add it to the file system queue

Downloading
-----------

### API

Downloads are added by using the `downloadqadd` endpoint and are removed 
using `downloadqremove`. There is also support for changing
the order of the elements in the list via `downloadqmove` and for getting the 
status of the download system as a whole through `downloadqget`.

Once completed the downloads will show up in `completedqget`. Can be cleared 
using `completedqclear`.

### Client

The API simply deposits the request in `app.download_q` under destination 
peer id. The file system module (through `peer_q_download`) checks if the
peer is responsive and, if so, ensures the correspondence between first
member of `app.download_q` and `client_downloading`:
- for downloads in progress the function checks if the download 
is completed and, if so, removes the entry from the `app.download_q`.
- for new downloads `client_downloading_pending_chunks` and
`client_downloading_requested_chunks` are reset to empty lists.
`client_downloading_file_name` stores the name of the file being downloaded
`client_downloading_status`
`client_downloading_chunks_last_received`

`client_downloading_pending_chunks` is initialized to store
a list of chunks, each with its own id. `client_downloading_status`
also stores one entry for each peer and each chunk.

`peer_download` will send at most FILESYSTEM_CREDIT_MAX requests
to connected peer, taking the chunks out of *pending* and placing
them on *requested*. `client_downloading_status` is initialized
to a tuple that stores the time this request was sent.

The async replies are stored in `chunk_requests_ack_queue`
