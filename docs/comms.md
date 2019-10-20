Communication
=============

Each instance creates a single server and as much clients as there are
peers connected. A fappli

Server
------

A single socket of type REPly is created and connected to local
app address and port (indicated by app-addr and app-port startup options).
All peers will connect to this single slot for sending commands/requests
and receiving replies.

Client
------

One DEALER socket is created for each peer and bound to remote app address.
The client sends requests/commands to the server and expects replies.


Hart beat
---------

Also called a rollcall, it is executed for each connected peer from
time to time by the client. The data consists of a standard request as
created by TacoCommands.create_request() with a NET_REQUEST of 
NET_REQUEST_ROLLCALL.

The TacoCommands.process_request() routes the request to 
TacoCommands.reply_rollcall_cmd()