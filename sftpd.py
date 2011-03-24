#!/usr/bin/python
"""
Expose an CloudFileFS object over SFTP using paramkino
"""

import logging

import os
import stat as statinfo
import time
from SocketServer import StreamRequestHandler, TCPServer
import threading

import paramiko

from ftpcloudfs.fs import CloudFilesFS
from StringIO import StringIO
from functools import wraps

from posixpath import basename #FIXME put in cloudfilesfs?

# Default host key used by CloudFilesSFTPServer
#
DEFAULT_HOST_KEY = paramiko.RSAKey.from_private_key(StringIO("-----BEGIN RSA PRIVATE KEY-----\nMIICXgIBAAKCAIEAl7sAF0x2O/HwLhG68b1uG8KHSOTqe3Cdlj5i/1RhO7E2BJ4B\n3jhKYDYtupRnMFbpu7fb21A24w3Y3W5gXzywBxR6dP2HgiSDVecoDg2uSYPjnlDk\nHrRuviSBG3XpJ/awn1DObxRIvJP4/sCqcMY8Ro/3qfmid5WmMpdCZ3EBeC0CAwEA\nAQKCAIBSGefUs5UOnr190C49/GiGMN6PPP78SFWdJKjgzEHI0P0PxofwPLlSEj7w\nRLkJWR4kazpWE7N/bNC6EK2pGueMN9Ag2GxdIRC5r1y8pdYbAkuFFwq9Tqa6j5B0\nGkkwEhrcFNBGx8UfzHESXe/uE16F+e8l6xBMcXLMJVo9Xjui6QJBAL9MsJEx93iO\nzwjoRpSNzWyZFhiHbcGJ0NahWzc3wASRU6L9M3JZ1VkabRuWwKNuEzEHNK8cLbRl\nTyH0mceWXcsCQQDLDEuWcOeoDteEpNhVJFkXJJfwZ4Rlxu42MDsQQ/paJCjt2ONU\nWBn/P6iYDTvxrt/8+CtLfYc+QQkrTnKn3cLnAkEAk3ixXR0h46Rj4j/9uSOfyyow\nqHQunlZ50hvNz8GAm4TU7v82m96449nFZtFObC69SLx/VsboTPsUh96idgRrBQJA\nQBfGeFt1VGAy+YTLYLzTfnGnoFQcv7+2i9ZXnn/Gs9N8M+/lekdBFYgzoKN0y4pG\n2+Q+Tlr2aNlAmrHtkT13+wJAJVgZATPI5X3UO0Wdf24f/w9+OY+QxKGl86tTQXzE\n4bwvYtUGufMIHiNeWP66i6fYCucXCMYtx6Xgu2hpdZZpFw==\n-----END RSA PRIVATE KEY-----\n"))


def return_sftp_errors(func):
    """Decorator to catch EnvironmentError~s and return SFTP error codes instead.

    Other exceptions are not caught.
    """
    @wraps(func)
    def wrapper(*args,**kwargs):
        try:            
            return func(*args,**kwargs)            
        except EnvironmentError, e:
            return paramiko.SFTPServer.convert_errno(e.errno)
    return wrapper


class SFTPServerInterface(paramiko.SFTPServerInterface):
    """
    SFTPServerInterface implementation that exposes a CloudFilesFS object
    """

    def __init__(self, server, fs, *args, **kwargs):
        self.fs = fs
        super(SFTPServerInterface,self).__init__(server, *args, **kwargs)

    @return_sftp_errors
    def open(self, path, flags, attr):
        return SFTPHandle(self, path, flags)

    @return_sftp_errors
    def list_folder(self, path):
        return [ paramiko.SFTPAttributes.from_stat(stat, leaf)
                 for leaf, stat in self.fs.listdir_with_stat(path) ]
 
    @return_sftp_errors
    def stat(self, path):
        stat = self.fs.stat(path)
        filename = basename(path)
        return paramiko.SFTPAttributes.from_stat(stat, path)

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
        return self.fs.abspath(self.fs.normpath(path))

    @return_sftp_errors
    def chattr(self, path, attr):
        return paramiko.SFTP_OP_UNSUPPORTED

    def readlink(self, path):
        return paramiko.SFTP_OP_UNSUPPORTED

    def symlink(self, path):
        return paramiko.SFTP_OP_UNSUPPORTED


class SFTPHandle(paramiko.SFTPHandle):
    """
    Expose a CloudFilesFD object to SFTP
    """

    def __init__(self, owner, path, flags):
        super(SFTPHandle, self).__init__(flags)
        self.owner = owner
        self.path = path
        logging.debug("SFTPHandle(path=%r, flags=%r)" % (path, flags))
        open_mode = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
        if open_mode == os.O_RDONLY:
            mode = "r"
        elif open_mode == os.O_WRONLY:
            mode = "w"
        elif open_mode == os.O_RDWR:
            mode = "rw"
        else:
            logging.error("Bad open mode %r" % flags)
            return parmiko.SFTP_OP_UNSUPPORTED
        if flags & os.O_APPEND:
            mode += "+"
        # FIXME ignores os.O_CREAT, os.O_TRUNC, os.O_EXCL
        self._file = owner.fs.open(path, mode)
        self._tell = 0

    @return_sftp_errors
    def close(self):
        self._file.close()
        return paramiko.SFTP_OK

    @return_sftp_errors
    def read(self, offset, length):
        if offset != self._tell:
            return paramiko.SFTP_OP_UNSUPPORTED
            # FIXME self._file.seek(offset)
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
        return paramiko.SFTP_OK

    def stat(self):
        return self.owner.stat(self.path)

    def chattr(self,attr):
        return SFTP_OP_UNSUPPORTED


class CloudFilesSFTPRequestHandler(StreamRequestHandler):
    """
    SocketServer RequestHandler subclass for CloudFilesSFTPServer.

    This RequestHandler subclass creates a paramiko Transport, sets up the
    sftp subsystem, and hands off to the transport's own request handling
    thread.  Note that paramiko.Transport uses a separate thread by default,
    so there is no need to use ThreadingMixin.
    """

    def handle(self):
        t = paramiko.Transport(self.request)
        t.add_server_key(self.server.host_key)
        t.set_subsystem_handler("sftp", paramiko.SFTPServer, SFTPServerInterface, self.server.fs)
        # Note that this actually spawns a new thread to handle the requests.
        # (Actually, paramiko.Transport is a subclass of Thread)
        t.start_server(server=self.server)


class CloudFilesSFTPServer(TCPServer, paramiko.ServerInterface):
    """
    Expose a CloudFilesFS object over SFTP
    """
    allow_reuse_address = True

    def __init__(self, address, host_key=None, authurl=None):
        self.fs = CloudFilesFS(None, None, authurl=authurl) # unauthorized
        self.host_key = host_key or DEFAULT_HOST_KEY
        TCPServer.__init__(self, address, CloudFilesSFTPRequestHandler)

    def close_request(self, request):
        # do nothing paramiko.Transport deals with it
        pass

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_none(self, username):
        """Check whether the user can proceed without authentication."""
        return paramiko.AUTH_FAILED

    def check_auth_publickey(self, username, key):
        """Check whether the given public key is valid for authentication."""
        return paramiko.AUTH_FAILED

    def check_auth_password(self, username, password):
        """Check whether the given password is valid for authentication."""
        try:
            self.fs.authenticate(username, password)
        except EnvironmentError, e:
            logging.error("Failed to authenticate: %s" % e)
            return paramiko.AUTH_FAILED
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self,username):
        """Return string containing a comma separated list of allowed auth modes.

        The available modes are  "node", "password" and "publickey".
        """
        return "password"

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    server = CloudFilesSFTPServer(("localhost",8022), authurl='https://external.cloudstorage.dev.bofhs.net/v1.0')
    try:
        server.serve_forever()
    except (SystemExit,KeyboardInterrupt):
        server.server_close()

