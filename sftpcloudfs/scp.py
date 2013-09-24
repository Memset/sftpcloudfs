import stat
import optparse
import posixpath


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

    @classmethod
    def get_argparser(cls):
        try:
            return cls.arg_parser
        except AttributeError:
            cls.arg_parser = parser = optparse.OptionParser(
                prog='scp',
                description='Remote part of secure copy tool'
            )
            parser.add_option('-v', action='count', dest='verbose',
                              help='makes SCP verbose')
            parser.add_option('-t', action='store_true', dest='copy_to')
            parser.add_option('-f', action='store_true', dest='copy_from')
            parser.add_option('-r', action='store_true', dest='recursive',
                              help='Recursively copy entire directories.')
            parser.add_option('-p', action='store_true', dest='preserve',
                              help='Preserves modification times, access '
                                   'times, and modes from the original file.')
            parser.add_option('-d', action='store_true', dest='directory',
                              help='Target should be a directory')
            parser.add_option('-E', action='store_true', dest='xargs',
                              help='Target should be a directory')

            def ap_exit(status=0, message=""):
                raise SCPException(status, message)

            parser.exit = ap_exit
            parser.error = lambda msg: ap_exit(2, msg)

            return parser

    def main(self):
        try:
            self.args, self.paths = self.get_argparser().parse_args(self.args)
            self.log.debug("SCP %r", self.args)

            if self.args.copy_to and self.args.copy_from:
                raise SCPException(4, "-t and -f cannot be combined")

            if len(self.paths) != 1:
                raise SCPException(4, "scp takes exacly one path")

            if self.args.copy_to:
                self.receive()
            elif self.args.copy_from:
                path = self.paths[0]
                path_stat = self.fs.stat(path)

                self.send(path, path_stat)
            else:
                raise SCPException(4, "Missing -t or -f argument")
        except SCPException, ex:
            self.log.info("SCP reject: %s", ex)
            self.channel.sendall('\x01scp: ')
            self.channel.sendall(str(ex))
            self.channel.sendall('\n')
            self.channel.send_exit_status(ex.status)
            self.channel.close()
        except:
            self.log.exception("SCP interal exception")
            self.channel.sendall('\x01scp: internal error\n')
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

        line, self.buffer = self.buffer.split('\n', 1)
        return line

    def receive(self):
        # Ack the connection
        self.channel.send('\x00')

        if self.args.directory:
            directory = self.paths[0]
            filename = None
        else:
            directory, filename = posixpath.split(self.paths[0])

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
            self.channel.send('\x00')
            record = self.recv_line()

        if record[0] == 'C':
            mode, size, name = record[1:].split()
            size = int(size)
            tgt_path = path + '/' + (override_name or name)

            if self.fs.isdir(tgt_path):
                raise SCPException(1, '%s: directory exists' % tgt_path)

            # ACK this file record
            self.channel.send('\x00')

            fd = self.fs.open(tgt_path, 'w')

            bytes_sent = 0
            while bytes_sent < size:
                chunk = self.recv(64*1024)
                fd.write(chunk)
                bytes_sent += len(chunk)

            fd.close()
            # ACK sending this file
            self.channel.send('\x00')
            #self.wait_for_ack()

        elif record[0] == 'D':
            mode, size, name = record[1:].split()

            tgt_path = path + '/' + (override_name or name)

            if self.fs.isfile(tgt_path):
                raise SCPException(1, '%s: file exists', tgt_path)

            # ACK this directory record
            self.channel.send('\x00')

            self.fs.mkdir(tgt_path)

            while True:
                record = self.recv_line()
                if record[0] == 'E':
                    # ACK this file record
                    self.channel.send('\x00')
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
            self.channel.send('\x00')
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
