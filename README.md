TacoZMQ
=======

TacoZMQ is a friend to friend [darknet](http://en.wikipedia.org/wiki/Darknet_%28file_sharing%29) written in [Python](http://www.python.org) and [ZeroMQ](http://www.zeromq.org).

Current Features
----------------

 * Linux variants only for now.
 * Encryption done using the [Curve25519 elliptic curve cryptography (ECC) algorithm](http://en.wikipedia.org/wiki/Curve25519)
 * Self-healing web of peers
  * When someone adds a new peer, their information is spread to all other peers automatically. Each user can then enable that peer if they choose to.
 * File transfers with a download queue.
 * Configurable upload and download rate limits

Planned Features
----------------

 * Directory Downloading
 * Peer Searching
 * Subscibing to a directory to monitoring and download all future updates
 * Put in a issue/feature request if you want something added!
 * Windows + MacOS support.

Install
-------

TacoZMQ is not available in pypi.org, so you need to either clone the
repository or download an archive from github.com.

Once the directory is on your machine cd into it and:

### Windows

copy setup.bat to setup.bat and change values to match your environment.
Then call setup.bat each time you want to activate the environment.
On first run it will create a virtual environment and will run setup.py

Note that Windows support is experimental at this point, mostly 
because of file system issues.

To run it activate the environment and:

    python tacozmq.py --help
    
### Unices

    cd tacozmq
    python -m venv venv
    venv/Scripts/activate
    python setup.py # add develop if you plan to develop it
    python tacozmq.py --help


How It Works
------------

From an user's perspective the interface is accessed using the browser.
The application will create a small http server and it will inform you
that is listening at http://127.0.0.1:5340/ in  default configuration.
Point your browser to that address to get started.

The program also connects directly to peers. When you first start there will
be no peer. Install the program on a different computer (let's be honest, 
you have no peer :smiling_imp:) and go to `Settings -> Add peer`. Keep in mind
that this will not work out of the box if you ar behind a router; traffic
needs to be directed to your computer through port forwarding; to avoid 
confusions best use same port number on your computer and on the router.
