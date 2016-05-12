sftp cloudfs
============

This is a SFTP (Secure File Transfer Protocol) interface to OpenStack
Object Storage, providing a service that acts as a proxy between a
SFTP client and a storage service.

The username/password pair used to open the SFTP session is validated
using the authentication service of the files/storage service to get
an authentication token.

The communication between the client and the SFTP daemon is encrypted
all the time, and the SFTP service supports HTTPS communication with
the remote files/storage service.

There's limited SCP support since 0.10.


Install
-------

Requirements:

- python (2.6)
- paramiko (1.7.6+; 1.17.0+ recommended)
- python-swiftclient (2.0+)
- python-daemon (1.5.5)
- ftp-cloudfs (0.35+)
- python-memcached (1.45)

These are the minimum recommended versions based in our testing
environment.

You may need to create a host key with ssh-keygen.

To install the software, run following command:

    python setup.py install

Or using pip:

    pip install sftp-cloudfs

Please use the latest pip version, old versions may have bugs. You
can upgrade pip using pip: pip install --upgrade pip.


Usage
-----

Once installed you can run the service with sftpcloudfs executable,
that supports following options:

    --version             show program's version number and exit
    -h, --help            show this help message and exit
    -a AUTHURL, --auth-url=AUTHURL
                          Authentication URL
    --insecure            Allow to access servers without checking SSL certs
    -k HOST_KEY, --host-key-file=HOST_KEY
                          Host RSA key used by the server
    -b BIND_ADDRESS, --bind-address=BIND_ADDRESS
                          Address to bind (default: 127.0.0.1)
    -p PORT, --port=PORT  Port to bind (default: 8022)
    --memcache=MEMCACHE   Memcache server(s) to be used for cache (ip:port)
    -l LOG_FILE, --log-file=LOG_FILE
                          Log into provided file
    -f, --foreground      Run in the foreground (don't detach from terminal)
    --disable-scp         Disable SCP support (default: enabled)
    --syslog              Enable logging to system logger (daemon facility)
    -v, --verbose         Show detailed information on logging
    --pid-file=PID_FILE   Full path to the pid file location
    --uid=UID             UID to drop the privileges to when in daemon mode
    --gid=GID             GID to drop the privileges to when in daemon mode
    --keystone-auth       Use auth 2.0 (Keystone, requires keystoneclient)
    --keystone-region-name=REGION_NAME
                          Region name to be used in auth 2.0
    --keystone-tenant-separator=TENANT_SEPARATOR
                          Character used to separate tenant_name/username in
                          auth 2.0, default: TENANT.USERNAME
    --keystone-service-type=SERVICE_TYPE
                          Service type to be used in auth 2.0, default: object-
                          store
    --keystone-endpoint-type=ENDPOINT_TYPE
                          Endpoint type to be used in auth 2.0, default:
                          publicURL
    --config=CONFIG       Use an alternative configuration file

The default location for the configuration file is /etc/sftpcloudfs.conf.

Memcache is optional but highly recommended for better performance. Any Memcache
server must be secured to prevent unauthorized access to the cached data.

By default Swift auth 1.0 will be used, and is compatible with OpenStack
Object Storage (Swift) using swauth authentication middleware.

Optionally OpenStack Identity Service 2.0 (*aka* keystone) can be used. Currently
python-keystoneclient (0.3.2+) is required to use auth 2.0 and it can be enabled
with *--keystone-auth* option. 

The server supports large files (over the 5GB default) by splitting the files
in parts into a *.part* subdirectory and using a manifest file to access them as
a single file.

Please check the example configuration file for further details.


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
- Koert van der Veer <koert@cloudvps.com>

