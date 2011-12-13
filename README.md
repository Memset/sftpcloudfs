sftpd cloudfs
=============

This is a SFTP (Secure File Transfer Protocol) interface to Rackspace
Cloud Files and OpenStack Object Storage, providing a service that
acts as a proxy between a SFTP client and a remote files/storage
service.

The username/password pair used to open the SFTP session is validated
using the authentication service of the files/storage service to get
an authentication token.

The communication between the client and the SFTP daemon is encrypted
all the time, and the SFTP service supports HTTPS communication with
the remote files/storage service.


Install
-------

Requirements:

- python (2.6)
- paramiko (1.7.6)
- python-cloudfiles (1.7.9)
- python-daemon (1.5.5)
- ftp-cloudfs (0.9)

These are the minimum recommended versions based in our testing
environment.

You may need to create a host key with ssh-keygen.

To install the software, run following command:

    python setup.py install

Or using pip:

    pip install sftp-cloudfs

Please use the latest pip version, old versions may have bugs. You
can upgrade pip using pip: pip install --upgrade pip.

Or using Debian packaging:

    debuild -us -uc

and then:

    dpkg -i sftpcloudfs_VERSION-1_all.deb


Usage
-----

Once installed you can run the service with sftpcloudfs executable,
that supports following options:

    --version             show program's version number and exit
    -h, --help            show this help message and exit
    -a AUTHURL, --auth-url=AUTHURL
                          Authentication URL
    -k HOST_KEY, --host-key-file=HOST_KEY
                          Host RSA key used by the server
    -b BIND_ADDRESS, --bind-address=BIND_ADDRESS
                          Address to bind (default: 127.0.0.1)
    -p PORT, --port=PORT  Port to bind (default: 8022)
    -l LOG_FILE, --log-file=LOG_FILE
                          Log into provided file
    -f, --foreground      Run in the foreground (don't detach from terminal)
    --syslog              Enable logging to system logger (daemon facility)
    -v, --verbose         Show detailed information on logging
    --pid-file=PID_FILE   Pid file location when in daemon mode
    --uid=UID             UID to drop the privileges to when in daemon mode
    --gid=GID             GID to drop the privileges to when in daemon mode
    --config=CONFIG       Use an alternative configuration file

The default location for the configuration file is /etc/sftpcloudfs.conf.


License
-------

This is free software under the terms of MIT license (check COPYING file
included in this package).

The server is loosely based on the BSD licensed sftpd server code from:

    http://code.google.com/p/pyfilesystem/


Contact and support
-------------------

The project website is at:

  https://github.com/memset/sftpcloudfs

There you can file bug reports, ask for help or contribute patches.


Authors
-------

- Nick Craig-Wood <nick@memset.com>
- Juan J. Martinez <juan@memset.com>

Contributors
------------

- Christophe Le Guern <c35sys@gmail.com>

