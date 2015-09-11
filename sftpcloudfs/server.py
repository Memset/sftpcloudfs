#!/usr/bin/python
"""
Expose a CloudFileFS object over SFTP using paramiko

Copyright (C) 2011-2015 by Memset Ltd. http://www.memset.com/

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

import logging

import os
import errno
import shlex
from time import time
import threading
from SocketServer import StreamRequestHandler, ForkingTCPServer

import paramiko
from Crypto import Random

from ftpcloudfs.fs import ObjectStorageFS, ObjectStorageFD
from ftpcloudfs.utils import smart_str
from sftpcloudfs.scp import SCPHandler

from functools import wraps
from posixpath import basename

def return_sftp_errors(func):
    """
    Decorator to catch EnvironmentError~s and return SFTP error codes instead.

    Other exceptions are logged and processed as EIO errors.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        log = paramiko.util.get_logger("paramiko")
        name = getattr(func, "func_name", "unknown")
        try:
            log.debug("%s(%r,%r): enter" % (name, args, kwargs))
            rc = func(*args, **kwargs)
        except BaseException, e:
            obj = args[0]
            params = args[1:] if len(args) > 1 else ()
            msg = "%s%r from %r: %s" % (name, params, obj.client_address, e)
            if isinstance(e, EnvironmentError):
                log.info(msg)
                error = e.errno
            else:
                log.exception("unexpected error: %s" % msg)
                error = errno.EIO
            rc = paramiko.SFTPServer.convert_errno(error)
        log.debug("%s: returns %r" % (name, rc))
        return rc
    return wrapper


class SFTPServerInterface(paramiko.SFTPServerInterface):
    """
    SFTPServerInterface implementation that exposes a ObjectStorageFS object.
    """

    def __init__(self, server, fs, *args, **kwargs):
        self.fs = fs
        self.client_address = server.client_address
        self.log = paramiko.util.get_logger("paramiko")
        self.log.debug("%s: start filesystem interface" % self.__class__.__name__)
        super(SFTPServerInterface,self).__init__(server, *args, **kwargs)

    @return_sftp_errors
    def open(self, path, flags, attr):
        return SFTPHandle(self, path, flags)

    @return_sftp_errors
    def list_folder(self, path):
        return [ paramiko.SFTPAttributes.from_stat(stat, smart_str(leaf))
                 for leaf, stat in self.fs.listdir_with_stat(path) ]

    @return_sftp_errors
    def stat(self, path):
        stat = self.fs.stat(path)
        filename = basename(path)
        return paramiko.SFTPAttributes.from_stat(stat, filename)

    def lstat(self, path):
        return self.stat(path)

    @return_sftp_errors
    def remove(self, path):
        self.fs.remove(path)
        return paramiko.SFTP_OK

    @return_sftp_errors
    def rename(self, oldpath, newpath):
        self.fs.rename(oldpath, newpath)
        return paramiko.SFTP_OK

    @return_sftp_errors
    def mkdir(self, path, attr):
        self.fs.mkdir(path)
        return paramiko.SFTP_OK

    @return_sftp_errors
    def rmdir(self, path):
        self.fs.rmdir(path)
        return paramiko.SFTP_OK

    def canonicalize(self, path):
        return smart_str(self.fs.abspath(self.fs.normpath(path)))

    @return_sftp_errors
    def chattr(self, path, attr):
        return paramiko.SFTP_OP_UNSUPPORTED

    def readlink(self, path):
        return paramiko.SFTP_OP_UNSUPPORTED

    def symlink(self, path):
        return paramiko.SFTP_OP_UNSUPPORTED


class SFTPHandle(paramiko.SFTPHandle):
    """
    Expose a ObjectStorageFD object to SFTP.
    """

    def __init__(self, owner, path, flags):
        super(SFTPHandle, self).__init__(flags)
        self.log = paramiko.util.get_logger("paramiko")
        self.owner = owner
        self.path = path
        self.log.debug("SFTPHandle(path=%r, flags=%r)" % (path, flags))
        open_mode = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
        if open_mode == os.O_RDONLY:
            mode = "r"
        elif open_mode == os.O_WRONLY:
            mode = "w"
        elif open_mode == os.O_RDWR:
            mode = "rw"
        else:
            self.log.error("Bad open mode %r" % flags)
            return paramiko.SFTP_OP_UNSUPPORTED
        if flags & os.O_APPEND:
            mode += "+"

        # we need the file size for r & rw mode; this needs to be performed
        # BEFORE open so the cache gets invalidated in write operations
        try:
            self._size = owner.fs.stat(path).st_size
        except EnvironmentError:
            self._size = 0

        # FIXME ignores os.O_CREAT, os.O_TRUNC, os.O_EXCL
        self._file = owner.fs.open(path, mode)
        self._tell = 0

    @property
    def client_address(self):
        return self.owner.client_address

    @return_sftp_errors
    def close(self):
        self._file.close()
        return paramiko.SFTP_OK

    @return_sftp_errors
    def read(self, offset, length):
        if offset != self._tell:
            # this is not an "invalid offset" error
            if offset > self._size:
                return paramiko.SFTP_EOF
            self._file.seek(offset)
            self._tell = offset
        data = self._file.read(length)
        self._tell += len(data)
        return data

    @return_sftp_errors
    def write(self, offset, data):
        if offset != self._tell:
            return paramiko.SFTP_OP_UNSUPPORTED
            # FIXME self._file.seek(offset)
        self._file.write(data)
        self._tell += len(data)
        # update the file size
        if self._tell > self._size:
            self._size = self._tell
        return paramiko.SFTP_OK

    def stat(self):
        return self.owner.stat(self.path)

    def chattr(self,attr):
        return paramiko.SFTP_OP_UNSUPPORTED


class ObjectStorageSFTPRequestHandler(StreamRequestHandler):
    """
    SocketServer RequestHandler subclass for ObjectStorageSFTPServer.

    This RequestHandler subclass creates a paramiko Transport, sets up the
    sftp subsystem, and hands off to the transport's own request handling
    thread.  Note that paramiko.Transport uses a separate thread by default,
    so there is no need to use ThreadingMixin.

    A TERM signal may be processed with a delay up to 10 seconds.
    """

    timeout = 60
    # these are set by the server
    auth_timeout = None
    negotiation_timeout = 0
    keepalive = 0
    secopts = {}

    def handle(self):
        Random.atfork()
        paramiko.util.get_logger("paramiko.transport").setLevel(logging.CRITICAL)
        self.log = paramiko.util.get_logger("paramiko")
        self.log.debug("%s: start transport" % self.__class__.__name__)
        self.server.client_address = self.client_address
        t = paramiko.Transport(self.request)
        if self.secopts:
            secopt = t.get_security_options()
            for op, val in self.secopts.items():
                try:
                    setattr(secopt, op, val)
                except ValueError as ex:
                    self.log.error("Failed to setup %s (%r): %s" % (op, val, ex))
                else:
                    self.log.debug("%s set to %r" % (op, val))
        t.add_server_key(self.server.host_key)
        if self.keepalive:
            self.log.debug("%s: setting keepalive to %d" % (self.__class__.__name__, self.keepalive))
            t.set_keepalive(self.keepalive)
        t.set_subsystem_handler("sftp", paramiko.SFTPServer, SFTPServerInterface, self.server.fs)

        # asynchronous negotiation with optional time limit; paramiko has a banner timeout already (15 secs)
        start = time()
        event = threading.Event()
        try:
            t.start_server(server=self.server, event=event)
            while True:
                if event.wait(0.1):
                    if not t.is_active():
                        ex = t.get_exception() or "Negotiation failed."
                        self.log.warning("%r, disconnecting: %s" % (self.client_address, ex))
                        return
                    self.log.debug("negotiation was OK")
                    break
                if self.negotiation_timeout > 0 and time()-start > self.negotiation_timeout:
                    self.log.warning("%r, disconnecting: Negotiation timed out." % (self.client_address,))
                    return

            chan = t.accept(self.auth_timeout)
            if chan is None:
                self.log.warning("%r, disconnecting: auth failed, channel is None." % (self.client_address,))
                return

            while t.isAlive():
                t.join(timeout=10)
        finally:
            self.log.info("%r, cleaning up connection: bye." % (self.client_address,))
            if self.server.fs.conn:
                self.server.fs.conn.close()
            t.close()
        return

class ObjectStorageSFTPServer(ForkingTCPServer, paramiko.ServerInterface):
    """
    Expose a ObjectStorageFS object over SFTP.
    """
    allow_reuse_address = True

    def __init__(self, address, host_key=None, authurl=None, max_children=20, keystone=None,
            no_scp=False, split_size=0, hide_part_dir=False, auth_timeout=None,
            negotiation_timeout=0, keepalive=0, insecure=False, secopts=None):
        self.log = paramiko.util.get_logger("paramiko")
        self.log.debug("%s: start server" % self.__class__.__name__)
        self.fs = ObjectStorageFS(None, None, authurl=authurl, keystone=keystone, hide_part_dir=hide_part_dir, insecure=insecure) # unauthorized
        self.host_key = host_key
        self.max_children = max_children
        self.no_scp = no_scp
        ObjectStorageSFTPRequestHandler.auth_timeout = auth_timeout
        ObjectStorageSFTPRequestHandler.negotiation_timeout = negotiation_timeout
        ObjectStorageSFTPRequestHandler.keepalive = keepalive
        ObjectStorageSFTPRequestHandler.secopts = secopts
        ForkingTCPServer.__init__(self, address, ObjectStorageSFTPRequestHandler)
        ObjectStorageFD.split_size = split_size

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        self.log.warning("Channel request denied from %s, kind=%s" \
                         % (self.client_address, kind))
        # all the check_channel_*_request return False by default but
        # sftp subsystem because of the set_subsystem_handler call in
        # the ObjectStorageSFTPRequestHandler
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        """Determine if a shell command will be executed for the client."""

        # Parse the command
        if ' -- ' in command:
            # scp will use -- to delimit the begining of the unscaped filename
            # so translate it to something that shelex can manage
            command = command.replace(' -- ', ' "') + '"'
        command = shlex.split(command)
        self.log.debug('check_channel_exec_request %r' % command)

        try:
            if command[0] == 'scp':
                if self.no_scp:
                    self.log.info("scp exec request denied from=%s (scp is disabled)" % (self.client_address,))
                    return False
                self.log.info('invoking %r from=%s' % (command, self.client_address))
                # handle the command execution
                SCPHandler(command[1:], channel, self.fs, self.log).start()
                return True
        except:
            self.log.exception("command %r failed from=%s" % (command, self.client_address))
            return False

        return False

    def check_auth_none(self, username):
        """Check whether the user can proceed without authentication."""
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        """Check whether the given public key is valid for authentication."""
        return paramiko.AUTH_FAILED

    def check_auth_password(self, username, password):
        """Check whether the given password is valid for authentication."""
        self.log.info("Auth request (type=password), username=%s, from=%s" \
                      % (username, self.client_address))
        try:
            if not password:
                raise EnvironmentError("no password provided")
            self.fs.authenticate(username, password)
        except EnvironmentError, e:
            self.log.warning("%s: Failed to authenticate: %s" % (self.client_address, e))
            self.log.error("Authentication failure for %s from %s port %s" % (username,
                           self.client_address[0], self.client_address[1]))
            return paramiko.AUTH_FAILED
        self.fs.conn.real_ip = self.client_address[0]
        self.log.info("%s authenticated from %s" % (username, self.client_address))
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self,username):
        """Return string containing a comma separated list of allowed auth modes.

        The available modes are  "node", "password" and "publickey".
        """
        return "password"

