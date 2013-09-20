import stat
import threading

import argparse
import posixpath

arg_parser = argparse.ArgumentParser(
    prog='scp',
    description='Remote part of secure copy tool'
)
arg_parser.add_argument('-verbose', '-v', action='count',
                        help='makes SCP verbose')
group = arg_parser.add_mutually_exclusive_group(required=True)
group.add_argument('--copy_to', '-t', action='store_true')
group.add_argument('--copy_from', '-f', action='store_true')
arg_parser.add_argument('--recursive', '-r', action='store_true',
                        help='Recursively copy entire directories.')
arg_parser.add_argument('--preserve', '-p', action='store_true',
                        help='Preserves modification times, access '
                             'times, and modes from the original file.')
arg_parser.add_argument('--directory', '-d', action='store_true',
                        help='Target should be a directory')
arg_parser.add_argument('--xargs', '-E', action='store_true',
                        help='Target should be a directory')
arg_parser.add_argument('path', help='the path to process')


def ap_exit(status, message):
    raise SCPException(status, message)

arg_parser.exit = ap_exit
arg_parser.error = lambda msg: ap_exit(2, msg)


class SCPException(Exception):
    def __init__(self, status, message):
        self.status = status
        super(Exception, self).__init__(message)


class SCPHandler(object):

    def __init__(self, arguments, channel, fs, log):
        self.log = log
        self.channel = channel
        self.fs = fs
        self.args = arguments
        self.buffer = ""

        threading.Thread(target=self.main).start()

    def main(self):
        try:
            self.args = arg_parser.parse_args(self.args)
            self.log.debug("SCP %r", self.args)

            if self.args.copy_to:
                self.receive()
            elif self.args.copy_from:
                path = self.args.path
                path_stat = self.fs.stat(path)

                self.send(path, path_stat)
            else:
                raise SCPException(4, "Missing -t or -f argument")
        except SCPException, ex:
            self.channel.sendall('\001scp: ')
            self.channel.sendall(str(ex))
            self.channel.sendall('\n')
            self.channel.send_exit_status(ex.status)
            self.channel.close()
        except:
            self.log.exception("SCP interal exception")
            self.channel.sendall('\001scp: internal error\n')
            self.channel.send_exit_status(1)
            self.channel.close()
        else:
            self.channel.send_exit_status(0)
            self.channel.close()

    def recv(self, size):
        if self.buffer:
            result = self.buffer[:size]
            self.buffer = self.buffer[size:]
            return result

        return self.channel.recv(size)

    def recv_line(self):
        if '\n' not in self.buffer:
            while True:
                chunk = self.channel.recv(1024)
                self.buffer += chunk
                if '\n' in chunk:
                    break

        line, self.buffer = self.buffer.split('\n')
        return line

    def receive(self):
        # Ack the connection
        self.channel.send('\000')

        if self.args.directory:
            directory = self.args.path
            filename = None
        else:
            directory, filename = posixpath.split(self.args.path)

        if not self.fs.isdir(directory):
            raise SCPException(1, '%s is not a directory' % directory)

        record = self.recv_line()
        self.receive_inner(directory, record, override_name=filename)

    def receive_inner(self, path, record, override_name=None):

        if record[0] == 'T':
            # We're going to ignore this record, but for compatibility, we'll
            # confirm its arrival.

            # mtime, mtime_u, atime, atime_u = record[1:].split()
            # mtime = float(mtime) + float(mtime_u) / 100000
            # atime = float(atime) + float(atime_u) / 100000

            # ACK this file record
            self.channel.send('\000')
            record = self.recv_line()

        if record[0] == 'C':
            mode, size, name = record[1:].split()
            size = int(size)
            tgt_path = path + '/' + (override_name or name)

            if self.fs.isdir(tgt_path):
                raise SCPException(1, '%s: directory exists' % tgt_path)

            # ACK this file record
            self.channel.send('\000')

            fd = self.fs.open(tgt_path, 'w')

            bytes_sent = 0
            while bytes_sent < size:
                chunk = self.recv(64*1024)
                fd.write(chunk)
                bytes_sent += len(chunk)

            fd.close()
            # ACK sending this file
            self.channel.send('\000')
            #self.wait_for_ack()

        elif record[0] == 'D':
            mode, size, name = record[1:].split()

            tgt_path = path + '/' + (override_name or name)

            if self.fs.isfile(tgt_path):
                raise SCPException(1, '%s: file exists', tgt_path)

            # ACK this directory record
            self.channel.send('\000')

            self.fs.mkdir(tgt_path)

            while True:
                record = self.recv_line()
                if record[0] == 'E':
                    # ACK this file record
                    self.channel.send('\000')
                    break
                else:
                    self.receive_inner(tgt_path, record)

    def send(self, path, path_stat):
        self.log.debug('About to send %s', path)

        if self.args.preserve:
            self.channel.sendall("T%i 0 %i 0\n" % (
                                 path_stat.st_mtime,
                                 path_stat.st_atime))
            self.wait_for_ack()

        if stat.S_ISREG(path_stat.st_mode):
            self.channel.sendall("C%04o %i %s\n" % (
                                 path_stat.st_mode & 07777,
                                 path_stat.st_size,
                                 posixpath.basename(path)))
            self.wait_for_ack()

            fd = self.fs.open(path, 'r')
            while True:
                chunk = fd.read(64*1024)  # Fixme: magic number
                if chunk:
                    self.channel.sendall(chunk)
                else:
                    break

            # signal the end of the transfer
            self.channel.send('\000')
            self.wait_for_ack()

        elif not self.args.recursive:
            self.channel.sendall("scp: %s is not a regular file\n" % path)
            return 1
        else:
            self.channel.send("D%04o %i %s\n" % (
                              path_stat.st_mode & 07777,
                              0,
                              posixpath.basename(path)))

            self.wait_for_ack()

            for subpath, subpath_stat in self.fs.listdir_with_stat(path):
                subpath = path + "/" + subpath
                self.send_inner(subpath, subpath_stat)

            self.channel.send("E\n")
            self.wait_for_ack()

    def wait_for_ack(self):
        """ Wait for the ack byte """
        ack = self.channel.recv(1)
        if ack != '\x00':
            raise Exception("Command not acked (%r)" % ack)
