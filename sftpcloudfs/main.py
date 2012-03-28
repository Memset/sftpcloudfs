#!/usr/bin/python
"""
Main function to setup the daemon process.

Copyright (C) 2011, 2012 by Memset Ltd. http://www.memset.com/

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import os
import signal
import sys
import logging
from logging.handlers import SysLogHandler
from ConfigParser import RawConfigParser
from optparse import OptionParser
import daemon
import tempfile
from Crypto import Random
import paramiko
from sftpcloudfs.server import CloudFilesSFTPServer
from sftpcloudfs.constants import version, project_url, config_file
from ftpcloudfs.fs import CloudFilesFS

class PIDFile(object):
    """
    PID file implementation using a context manager.

    Entering the context acquires the lock, raising OSError if the file exists
    and it's already locked. Leaving the context cleans the PID file.

    Some methods are implemented for compatibility with lockfile and python-daemon.
    """
    def __init__(self, pidfile=None):
        self.pidfile = pidfile
        self._fd = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args, **kwargs):
        self.release()

    def acquire(self):
        pid = os.getpid()
        fd = os.open(self.pidfile, (os.O_CREAT|os.O_EXCL|os.O_WRONLY), 0644)
        self._fd = os.fdopen(fd, "w")
        self._fd.write("%s\n" % pid)
        self._fd.flush()
        return pid

    def is_locked(self):
        try:
            os.stat(self.pidfile)
        except OSError:
            return False
        else:
            return True

    def i_am_locking(self):
        return self._fd != None

    def release(self):
        if self._fd:
            self._fd.close()
            os.remove(self.pidfile)
            self._fd = None

class Main(object):
    def __init__(self):
        """Parse configuration and CLI options."""
        global config_file

        # look for an alternative configuration file
        try:
            alt_config_file = sys.argv.index('--config')
            alt_config_file = sys.argv[alt_config_file+1]
            config_file = alt_config_file
        except (ValueError, IndexError):
            pass

        config = RawConfigParser({'auth-url': None,
                                  'host-key-file': None,
                                  'bind-address': "127.0.0.1",
                                  'port': 8022,
                                  'memcache': None,
                                  'max-children': 20,
                                  'log-file': None,
                                  'syslog': 'no',
                                  'verbose': 'no',
                                  'pid-file': None,
                                  'uid': None,
                                  'gid': None,
                                  })

        config.read(config_file)
        if not config.has_section('sftpcloudfs'):
            config.add_section('sftpcloudfs')

        parser = OptionParser(version="%prog " + version,
                              description="This is a SFTP interface to Rackspace " + \
                                    "Cloud Files and Open Stack Object Storage (Swift).",
                              epilog="Contact and support at: %s" % project_url)

        parser.add_option("-a", "--auth-url", dest="authurl",
                          default=config.get('sftpcloudfs', 'auth-url'),
                          help="Authentication URL")

        parser.add_option("-k", "--host-key-file", dest="host_key",
                          default=config.get('sftpcloudfs', 'host-key-file'),
                          help="Host RSA key used by the server")

        parser.add_option("-b", "--bind-address", dest="bind_address",
                          default=config.get('sftpcloudfs', 'bind-address'),
                          help="Address to bind (default: 127.0.0.1)")

        parser.add_option("-p", "--port", dest="port",
                          type="int",
                          default=config.get('sftpcloudfs', 'port'),
                          help="Port to bind (default: 8022)")

        memcache = config.get('sftpcloudfs', 'memcache')
        if memcache:
            memcache = [x.strip() for x in memcache.split(',')]
        parser.add_option('--memcache',
                          type="str",
                          dest="memcache",
                          action="append",
                          default=memcache,
                          help="Memcache server(s) to be used for cache (ip:port)")


        parser.add_option("-l", "--log-file", dest="log_file",
                          default=config.get('sftpcloudfs', 'log-file'),
                          help="Log into provided file")

        parser.add_option("-f", "--foreground", dest="foreground",
                          action="store_true",
                          default=False,
                          help="Run in the foreground (don't detach from terminal)")

        parser.add_option("--syslog", dest="syslog",
                          action="store_true",
                          default=config.getboolean('sftpcloudfs', 'syslog'),
                          help="Enable logging to system logger (daemon facility)")

        parser.add_option("-v", "--verbose", dest="verbose",
                          action="store_true",
                          default=config.getboolean('sftpcloudfs', 'verbose'),
                          help="Show detailed information on logging")

        parser.add_option('--pid-file',
                          type="str",
                          dest="pid_file",
                          default=config.get('sftpcloudfs', 'pid-file'),
                          help="Pid file location when in daemon mode")

        parser.add_option('--uid',
                          type="int",
                          dest="uid",
                          default=config.get('sftpcloudfs', 'uid'),
                          help="UID to drop the privileges to when in daemon mode")

        parser.add_option('--gid',
                          type="int",
                          dest="gid",
                          default=config.get('sftpcloudfs', 'gid'),
                          help="GID to drop the privileges to when in daemon mode")

        parser.add_option('--config',
                          type="str",
                          dest="config",
                          default=config_file,
                          help="Use an alternative configuration file")

        (options, args) = parser.parse_args()

        # required parameters
        if not options.authurl:
            parser.error("No auth-url provided")

        if not options.host_key:
            parser.error("No host-key-file provided")

        try:
            self.host_key = paramiko.RSAKey(filename=options.host_key)
        except (IOError, paramiko.SSHException), e:
            parser.error("host-key-file: %s" % e)

        if not options.pid_file:
            options.pid_file = "%s/%s.pid" % (tempfile.gettempdir(), __package__)

        if options.memcache:
            CloudFilesFS.memcache_hosts = options.memcache
            try:
                CloudFilesFS(None, None)
            except (ValueError, TypeError):
                parser.error("memcache: invalid server address, ip:port expected")
        else:
            # default is True, and there's no single worker operation
            CloudFilesFS.single_cache = False

        self.pidfile = PIDFile(options.pid_file)
        if self.pidfile.is_locked():
            parser.error("pid-file found: %s\nIs the server already running?" % options.pid_file)

        options.max_children = config.get('sftpcloudfs', 'max-children')
        self.options = options

    def setup_log(self):
        """Setup server logging facility."""
        self.log = paramiko.util.get_logger("paramiko")

        if self.options.log_file:
            paramiko.util.log_to_file(self.options.log_file)

        if self.options.syslog is True:
            try:
                handler = SysLogHandler(address='/dev/log',
                                        facility=SysLogHandler.LOG_DAEMON)
            except IOError:
                # fall back to UDP
                handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON)
            finally:
                handler.setFormatter(logging.Formatter('%(name)s[%(_threadid)s]: %(levelname)s: %(message)s'))
                self.log.addHandler(handler)

        if self.options.foreground:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s: %(name)s[%(_threadid)s]: %(levelname)s: %(message)s'))
            self.log.addHandler(handler)

        if self.options.verbose:
            self.log.setLevel(logging.DEBUG)
            self.log.debug(self.options)
        else:
            self.log.setLevel(logging.INFO)


    def run(self):
        """Run the server."""
        server = CloudFilesSFTPServer((self.options.bind_address, self.options.port),
                                       host_key=self.host_key,
                                       authurl=self.options.authurl,
                                       max_children=self.options.max_children)

        dc = daemon.DaemonContext()
        dc.pidfile = self.pidfile

        if self.options.uid:
            dc.uid = self.options.uid

        if self.options.gid:
            dc.gid = self.options.gid

        # FIXME: we don't know the fileno for Random open files, but they're  < 16
        dc.files_preserve = range(server.fileno(), 16)

        if self.options.foreground:
            dc.detach_process = False
            dc.stderr = sys.stderr

        with dc:
            Random.atfork()
            self.setup_log()
            try:
                if os.getuid() == 0:
                    self.log.warning("UID is 0, running as root is not recommended")

                self.log.info("Listening on %s:%s" % (self.options.bind_address, self.options.port))
                server.serve_forever()
            except (SystemExit, KeyboardInterrupt):
                self.log.info("Terminating...")
                if server.active_children:
                    for pid in server.active_children:
                        os.kill(pid, signal.SIGTERM)
                server.server_close()

        if self.pidfile.i_am_locking():
            self.pidfile.release()

        return 0

