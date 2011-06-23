#!/usr/bin/python
"""
Main function to setup the daemon process.
"""

import os
import logging
from logging.handlers import SysLogHandler
from ConfigParser import RawConfigParser
from optparse import OptionParser
import daemon
from daemon.pidlockfile import PIDLockFile
import tempfile
from Crypto import Random
import paramiko
from sftpcloudfs.server import CloudFilesSFTPServer

version = "0.1"
project_url = "https://github.com/memset/blah"
config_file = "/etc/sftpcloudfs.conf"

class Main(object):
    def __init__(self):
        """Parse configuration and CLI options."""

        config = RawConfigParser({'auth-url': None,
                                  'host-key-file': None,
                                  'bind-address': "127.0.0.1",
                                  'port': 8022,
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
                          help="Authentication URL.")

        parser.add_option("-k", "--host-key-file", dest="host_key",
                          default=config.get('sftpcloudfs', 'host-key-file'),
                          help="Host RSA key used by the server.")

        parser.add_option("-b", "--bind-address", dest="bind_address",
                          default=config.get('sftpcloudfs', 'bind-address'),
                          help="Address to bind (default: 127.0.0.1).")

        parser.add_option("-p", "--port", dest="port",
                          type="int",
                          default=config.get('sftpcloudfs', 'port'),
                          help="Port to bind (default: 8022).")

        parser.add_option("-l", "--log-file", dest="log_file",
                          default=config.get('sftpcloudfs', 'log-file'),
                          help="Log into provided file.")

        parser.add_option("-f", "--foreground", dest="foreground",
                          action="store_true",
                          default=False,
                          help="Run in the foreground (don't detach from terminal).")

        parser.add_option("--syslog", dest="syslog",
                          action="store_true",
                          default=config.get('sftpcloudfs', 'syslog'),
                          help="Enable logging to system logger (daemon facility).")

        parser.add_option("-v", "--verbose", dest="verbose",
                          action="store_true",
                          default=config.get('sftpcloudfs', 'verbose'),
                          help="Show detailed information on logging.")

        parser.add_option('--pid-file',
                          type="str",
                          dest="pid_file",
                          default=config.get('sftpcloudfs', 'pid-file'),
                          help="Pid file location when in daemon mode.")

        parser.add_option('--uid',
                          type="int",
                          dest="uid",
                          default=config.get('sftpcloudfs', 'uid'),
                          help="UID to drop the privilige to when in daemon mode.")

        parser.add_option('--gid',
                          type="int",
                          dest="gid",
                          default=config.get('sftpcloudfs', 'gid'),
                          help="GID to drop the privilige to when in daemon mode.")

        (options, args) = parser.parse_args()

        if not options.pid_file:
            options.pid_file = "%s/%s.pid" % (tempfile.gettempdir(), __package__)

        try:
            os.stat(options.pid_file)
            parser.error("pid-file found: %s\nIs the server already running?" % options.pid_file)
        except OSError:
            pass

        # required parameters
        if not options.authurl:
            parser.error("No auth-url provided")

        if not options.host_key:
            parser.error("No host-key-file provided")

        try:
            self.host_key = paramiko.RSAKey(filename=options.host_key)
        except (IOError, paramiko.SSHException), e:
            parser.error("host-key-file: %s" % e)

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

        if self.options.verbose:
            self.log.setLevel(logging.DEBUG)
            self.log.debug(self.options)
        else:
            self.log.setLevel(logging.INFO)


    def run(self):
        """Run the server."""
        server = CloudFilesSFTPServer((self.options.bind_address, self.options.port),
                                       host_key=self.host_key,
                                       authurl=self.options.authurl)

        if self.options.foreground:
            self.setup_log()
            try:
                self.log.info("Listening on %s:%s" % (self.options.bind_address, self.options.port))
                server.serve_forever()
            except (SystemExit, KeyboardInterrupt):
                self.log.info("Terminating...")
                server.server_close()

            return 0

        dc = daemon.DaemonContext()

        self.pidfile = PIDLockFile(self.options.pid_file, threaded=True)
        dc.pidfile = self.pidfile

        if self.options.uid:
            dc.uid = self.options.uid

        if self.options.gid:
            dc.gid = self.options.gid

        # FIXME: we don't know the fileno for Random, but it's < 16
        dc.files_preserve = range(server.fileno(), 16)

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
                server.server_close()

        self.pidfile.release()

        return 0

