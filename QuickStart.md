# Quick Start

This is a recipe to start using sftpcloudfs for personal use.

## 1. Install sftpcloudfs and its dependencies

In this recipe we are going to use virtualenv and pip to unstall the
server. The package requires Python 2 (Python 3 is not supported).

You need to install **virtualenv**. I recommend you use your system's
package manager (if available).

For example, in Fedora you can install virtualenv running (as root):

``` yum install python-virtualenv ```

In Ubuntu/Debian you can run:

``` sudo apt-get install python-virtualenv ```

For other operating systems without package manager, please check:

    http://www.virtualenv.org/en/latest/#installation

### Setting a virtualenv environment

   1. Create a new virtualenv:

``` virtualenv ENV ```

   2. Activate it (example using BASH):

``` source ENV/bin/activate ```

   3. Upgrade pip (some distros package an outdated version of virtualenv):

``` pip install --upgrade pip ```

   4. Install sftp-cloudfs:

``` pip install sftp-cloudfs ```

Please note that some dependencies, such as **pycrypto** require your
system has a compiler installed (gcc) and Python development headers
(ie. python-devel in Fedora, python-dev in Debian/Ubuntu).

The install command will finish with something like this:

``` Successfully installed sftp-cloudfs paramiko python-swiftclient 
python-daemon python-memcached ftp-cloudfs pycrypto ecdsa simplejson 
lockfile pyftpdlib
Cleaning up... ``` 

You can verify the install with:

``` sftpcloudfs --version ```

***Important***: Please note that in order to use the server in the
future you'll need to activate the environment as we did in point 2.

## 2. Basic configuration

First you need to create a host key for the SFTP server:

``` ssh-keygen -t rsa -f `pwd`/rsa_key ```

Create it with no passphrase (just press enter when asked for a password).
This command will create two files in your current directory: rsa_key and
rsa_key.pub. We're not going to use the latter.

Now you need to know the authentication URL for the OpenStack Object Storage
service we're going to use.

For Rackspace (Cloud Files, compatible with OpenStack Object Storage):

 - US site: https://auth.api.rackspacecloud.com/v1.0
 - UK site: https://lon.auth.api.rackspacecloud.com/v1.0

Other OpenStack Object Storage providers will have a different URL,
for example:

 - Memset's Memstore: https://auth.storage.memset.com/v1.0
 - Memset's Memstore (keystone): https://auth.storage.memset.com/v2.0

The service can be configured creating a _/etc/sftpcloudfs.conf_ file,
but for sake of simplicity we're going to use command line options.

You can run the server with any regular user (root is not needed!):

``` sftpcloudfs -k rsa_key -a https://auth.storage.memset.com/v1.0 -f ```

(replace the auth URL as required, using Memstore in the example)

This will run the server at localhost and port 8022, you can stop the
server by pressing CTRL + C on the terminal where the server is running
(we're using the **-f** flag, that means 'foreground').

Now you can use our favourite SFTP client, for example:

``` sftp -oport=8022 127.0.0.1 ```

You'll need access credentials (user and password). Please refer to
your cloud storage provider's documentation.

### Troubleshooting

If there's any error, look for information in the terminal where the
server is running. Alternatively you can add **-v** flag to the server
command line and repeat the operation to get extra information (this is
very useful if you think you're found a bug and want to report it!).

## 3. A better configuration

Although the basic configuration can be enough for most uses, you may
want to use several connections at the same time to improve the server's
performance.

For that we recommend you to install **memcache** (again, use your
system's package manager), and run the server with:

``` sftpcloudfs -k rsa_key -a https://auth.storage.memset.com/v1.0 --memcache=127.0.0.1:11211 --syslog ```

This means:

  - We're using memcache as shared cache to speed up operations. Mecache
    needs to be installed and running on localhost port 11211 (default).
  - We're logging into the system logger (syslog). This is because we
    aren't using **-f** flag and now the server is detached from the
	terminal.

Note that you need to stop the server getting its PID from
/tmp/sftpcloudfs.pid and using **kill** command to send a SIGTERM
signal. You can use:

``` kill `cat /tmp/sftpcloudfs.pid` ```

Remember that you can check the system logger to verify the server is
running as you expect.

