#!/usr/bin/python
import unittest
import os
import sys
from swiftclient import client
import paramiko

hostname = "127.0.0.1"
port = 8022

# setup logging
#paramiko.util.log_to_file('test_sftpd.log')

class SftpcloudfsTest(unittest.TestCase):
    ''' FTP Cloud FS main test '''

    def setUp(self):
        if not all(['OS_API_KEY' in os.environ,
                    'OS_API_USER' in os.environ,
                    'OS_AUTH_URL' in os.environ,
                    ]):
            print "env OS_API_USER/OS_API_KEY/OS_AUTH_URL not found."
            sys.exit(1)

        self.username = os.environ['OS_API_USER']
        self.api_key = os.environ['OS_API_KEY']
        self.tenant = os.environ.get('OS_API_TENANT')
        self.auth_url = os.environ['OS_AUTH_URL']
        self.container = "sftpcloudfs_testing"

        connection_parameters = {
            "user": self.username,
            "key": self.api_key,
            "authurl": self.auth_url,
        }

        if self.tenant:
            connection_parameters['auth_version'] = 2
            connection_parameters['tenant_name'] = self.tenant

        self.conn = client.Connection(**connection_parameters)
        self.conn.put_container(self.container)

        self.transport = paramiko.Transport((hostname, port))
        self.transport.connect(
            username=self.username,
            password=self.api_key,
            # hostkey=hostkey
        )
        self.channel = self.transport.open_session()
        self.container = "sftpcloudfs_testing"

    def test_setup_and_teardown(self):
        pass

    def test_file_upload(self):
        # Source:
        # https://blogs.oracle.com/janp/entry/how_the_scp_protocol_works
        # Example 1

        self.channel.exec_command('scp -t /%s/foo' % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")


        self.channel.sendall("C0644 6 foo\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")
        self.channel.sendall("Hello\n")

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

        headers, content = self.conn.get_object(self.container, 'foo')
        self.assertEquals(content, 'Hello\n')

    def test_file_upload_to_dir(self):
        self.channel.exec_command('scp -td /%s' % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")


        self.channel.sendall("C0644 6 test\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")
        self.channel.sendall("Hello\n")

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

        headers, content = self.conn.get_object(self.container, 'test')
        self.assertEquals(content, 'Hello\n')

    def test_dir_upload(self):
        # Source:
        # https://blogs.oracle.com/janp/entry/how_the_scp_protocol_works
        # Example 1

        self.channel.exec_command('scp -tr /%s/foodir' % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("D0644 0 foodir\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("C0644 6 test\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("Hello\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("E\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

        headers, content = self.conn.get_object(self.container, 'foodir/test')
        self.assertEquals(content, 'Hello\n')

    def download_file(self):
        self.conn.put_object(self.container, 'bar', 'Hello\n')

        self.channel.exec_command('scp -f /%s/bar' % self.container)
        self.channel.send('\000' * 3)

        response = self.channel.read()

        self.assertEquals(response, 'C0644 6 bar\nHello\n')

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

    def download_dir(self):
        self.conn.put_object(self.container, 'foo/bar', 'Hello\n')

        self.channel.exec_command('scp -fr /%s/foo' % self.container)
        self.channel.send('\000' * 5)

        response = self.channel.read()

        self.assertEquals(
            response,
            'D0644 0 foo\n'
            'C0644 6 bar\nHello\n'
            'E\n'
        )

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

    def test_file_upload_invalid_size(self):
        self.channel.exec_command('scp -t /%s/foo' % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("C0644 not_an_integer test\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\001")

    def test_file_upload_error_disconnect(self):
        self.channel.exec_command('scp -t /%s/foo' % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("C0644 not_an_integer foo\n")
        # shouldn't raise and exception on the server
        # FIXME: test that it doesn't happen!

    def test_file_upload_unicode(self):
        self.channel.exec_command(u'scp -t /%s/Smiley\u263a\ file'.encode("utf-8") % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall(u"C0644 6 Smiley\u263a file\n".encode("utf-8"))
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")
        self.channel.sendall("Hello\n")

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

        headers, content = self.conn.get_object(self.container, u'Smiley\u263a file')
        self.assertEquals(content, 'Hello\n')

    def test_dir_upload_unicode(self):
        self.channel.exec_command(u'scp -tr /%s/Smiley\u263a\ dir'.encode("utf-8") % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall(u"D0644 6 Smiley\u263a dir\n".encode("utf-8"))
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("C0644 6 test\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("Hello\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall("E\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

        headers, content = self.conn.get_object(self.container, u'Smiley\u263a dir/test')
        self.assertEquals(content, 'Hello\n')

    def test_file_upload_like_scp(self):
        self.channel.exec_command('scp -t  -- /%s/file with spaces.txt' % self.container)

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        self.channel.sendall(u"C0644 6 file with spaces.txt\n")
        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")
        self.channel.sendall("Hello\n")

        ack = self.channel.recv(1)
        self.assertEquals(ack, "\000")

        exit_status = self.channel.recv_exit_status()
        self.assertEquals(exit_status, 0)

        tail = self.channel.recv(1)
        self.assertEquals(tail, '')

        headers, content = self.conn.get_object(self.container, 'file with spaces.txt')
        self.assertEquals(content, 'Hello\n')

    def tearDown(self):
        self.channel.close()
        self.transport.close()

        # Delete eveything from the container using the API
        _, fails = self.conn.get_container(self.container)
        for obj in fails:
            self.conn.delete_object(self.container, obj["name"])

        self.conn.delete_container(self.container)

if __name__ == '__main__':
    unittest.main()
