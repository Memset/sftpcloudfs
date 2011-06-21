#!/usr/bin/python
import unittest
import os
import sys
from datetime import datetime
from time import time
import cloudfiles
import paramiko
import stat

hostname = "127.0.0.1"
port = 8022

# setup logging
#paramiko.util.log_to_file('test_sftpd.log')

class SftpcloudfsTest(unittest.TestCase):
    ''' FTP Cloud FS main test '''

    def setUp(self):
        if not all(['RCLOUD_API_KEY' in os.environ,
                    'RCLOUD_API_USER' in os.environ]):
            print "env RCLOUD_API_USER or RCLOUD_API_KEY not found."
            sys.exit(1)

        self.username = os.environ['RCLOUD_API_USER']
        self.api_key = os.environ['RCLOUD_API_KEY']
        self.auth_url = os.environ.get('RCLOUD_AUTH_URL')

        self.transport = paramiko.Transport((hostname, port))
        self.transport.connect(username=self.username, password=self.api_key) #, hostkey=hostkey)
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)
        self.sftp.mkdir("/sftpcloudfs_testing")
        self.sftp.chdir("/sftpcloudfs_testing")
        self.conn = cloudfiles.get_connection(self.username, self.api_key, authurl=self.auth_url)
        self.container = self.conn.get_container('sftpcloudfs_testing')

    def create_file(self, path, contents):
        '''Create path with contents'''
        fd = self.sftp.open(path, "w")
        try:
            fd.write(contents)
        finally:
            fd.close()

    def read_file(self, path):
        '''Read contents of path'''
        fd = self.sftp.open(path, "r")
        try:
            return fd.read()
        finally:
            fd.close()

    def test_setup_and_teardown(self):
        pass

    def test_mkdir_chdir_rmdir(self):
        ''' mkdir/chdir/rmdir directory '''
        directory = "/foobarrandom"
        self.sftp.mkdir(directory)
        self.sftp.chdir(directory)
        self.assertEqual(self.sftp.getcwd(), directory)
        self.sftp.chdir("..")
        self.sftp.rmdir(directory)

    def test_mkdir_chdir_mkdir_rmdir_subdir(self):
        ''' mkdir/chdir/rmdir sub directory '''
        directory = "/foobarrandom"
        self.sftp.mkdir(directory)
        self.sftp.chdir(directory)
        self.assertEqual(self.sftp.getcwd(), directory)
        subdirectory = "potato"
        subdirpath = directory + "/" + subdirectory
        self.sftp.mkdir(subdirectory)
        # Can't delete a directory with stuff in
        self.assertRaises(EnvironmentError, self.sftp.rmdir, directory)
        self.sftp.chdir(subdirectory)
        self.assertEqual(self.sftp.getcwd(), subdirpath)
        self.sftp.chdir("..")
        self.assertEqual(self.sftp.getcwd(), directory)
        self.sftp.rmdir(subdirectory)
        self.sftp.chdir("..")
        self.sftp.rmdir(directory)

    def test_write_open_delete(self):
        ''' write/open/delete file '''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.sftp.stat("testfile.txt").st_size, len(content_string))
        retrieved = self.read_file("testfile.txt")
        self.assertEqual(retrieved, content_string)
        self.sftp.remove("testfile.txt")

    def test_write_open_delete_subdir(self):
        ''' write/open/delete file in a subdirectory'''
        self.sftp.mkdir("potato")
        self.sftp.chdir("potato")
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.sftp.stat("testfile.txt").st_size, len(content_string))
        retrieved = self.read_file("/sftpcloudfs_testing/potato/testfile.txt")
        self.assertEqual(retrieved, content_string)
        self.sftp.remove("testfile.txt")
        self.sftp.chdir("..")
        self.sftp.rmdir("potato")

    def test_write_to_slash(self):
        ''' write to slash should not be permitted '''
        self.sftp.chdir("/")
        content_string = "Hello Moto"
        self.assertRaises(EnvironmentError, self.create_file, "testfile.txt", content_string)

    def test_chdir_to_a_file(self):
        ''' chdir to a file '''
        self.create_file("testfile.txt", "Hello Moto")
        self.assertRaises(paramiko.SFTPError, self.sftp.chdir, "/sftpcloudfs_testing/testfile.txt")
        self.sftp.remove("testfile.txt")

    def test_chdir_to_slash(self):
        ''' chdir to slash '''
        self.sftp.chdir("/")

    def test_chdir_to_nonexistent_container(self):
        ''' chdir to non existent container'''
        self.assertRaises(EnvironmentError, self.sftp.chdir, "/i_dont_exist")

    def test_chdir_to_nonexistent_directory(self):
        ''' chdir to nonexistend directory'''
        self.assertRaises(EnvironmentError, self.sftp.chdir, "i_dont_exist")
        self.assertRaises(EnvironmentError, self.sftp.chdir, "/sftpcloudfs_testing/i_dont_exist")

    def test_listdir_root(self):
        ''' list root directory '''
        self.sftp.chdir("/")
        ls = self.sftp.listdir()
        self.assertTrue('sftpcloudfs_testing' in ls)
        self.assertTrue('potato' not in ls)
        self.sftp.mkdir("potato")
        ls = self.sftp.listdir()
        self.assertTrue('sftpcloudfs_testing' in ls)
        self.assertTrue('potato' in ls)
        self.sftp.rmdir("potato")

    def test_listdir(self):
        ''' list directory '''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEqual(self.sftp.listdir(), ["testfile.txt"])
        self.sftp.remove("testfile.txt")

    def test_listdir_attr(self):
        ''' list directory '''
        content_string = "Hello Moto"
        start = time()
        self.create_file("testfile.txt", content_string)
        ls = self.sftp.listdir_attr()
        self.assertEqual(len(ls), 1)
        ls = ls[0]
        self.assertEqual(ls.filename, "testfile.txt")
        self.assertEqual(ls.st_size, 10)
        dt = abs(ls.st_mtime - start)
        self.assertTrue(dt < 5.0, "timestamp for file is out by %r seconds (%r - %r)" % (dt, ls.st_mtime, start))
        self.assertEquals(ls.st_mode, stat.S_IFREG + 0644)
        self.sftp.remove("testfile.txt")

    def test_listdir_subdir(self):
        ''' list a sub directory'''
        content_string = "Hello Moto"
        self.create_file("1.txt", content_string)
        self.create_file("2.txt", content_string)
        start = time()
        self.sftp.mkdir("potato")
        self.create_file("potato/3.txt", content_string)
        self.create_file("potato/4.txt", content_string)
        self.assertEqual(self.sftp.listdir(), ["1.txt", "2.txt", "potato"])
        self.sftp.chdir("potato")
        self.assertEqual(self.sftp.listdir(), ["3.txt", "4.txt"])
        self.sftp.remove("3.txt")
        self.sftp.remove("4.txt")
        self.assertEqual(self.sftp.listdir(), [])
        self.sftp.chdir("..")
        self.sftp.remove("1.txt")
        self.sftp.remove("2.txt")
        self.assertEqual(self.sftp.listdir(), ["potato"])
        ls = self.sftp.listdir_attr()
        self.assertEqual(len(ls), 1)
        ls = ls[0]
        self.assertEqual(ls.filename, "potato")
        self.assertEqual(ls.st_size, 0)
        dt = abs(ls.st_mtime - start)
        self.assertTrue(dt < 5.0, "timestamp for dir is out by %r seconds (%r - %r)" % (dt, ls.st_mtime, start))
        self.assertEquals(ls.st_mode, stat.S_IFDIR + 0755)
        self.sftp.rmdir("potato")
        self.assertEqual(self.sftp.listdir(), [])

    def test_rename_file(self):
        '''rename a file'''
        content_string = "Hello Moto" * 100
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.sftp.stat("testfile.txt").st_size, len(content_string))
        self.assertRaises(EnvironmentError, self.sftp.stat, "testfile2.txt")
        self.sftp.rename("testfile.txt", "testfile2.txt")
        self.assertEquals(self.sftp.stat("testfile2.txt").st_size, len(content_string))
        self.assertRaises(EnvironmentError, self.sftp.stat, "testfile.txt")
        self.sftp.remove("testfile2.txt")

    def test_rename_file_into_subdir1(self):
        '''rename a file into a subdirectory 1'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.sftp.mkdir("potato")
        self.assertEquals(self.sftp.stat("testfile.txt").st_size, len(content_string))
        self.assertRaises(EnvironmentError, self.sftp.stat, "potato/testfile3.txt")
        self.sftp.rename("testfile.txt", "potato/testfile3.txt")
        self.assertEquals(self.sftp.stat("potato/testfile3.txt").st_size, len(content_string))
        self.assertRaises(EnvironmentError, self.sftp.stat, "testfile.txt")
        self.sftp.remove("potato/testfile3.txt")
        self.sftp.rmdir("potato")

    def test_rename_file_into_subdir2(self):
        '''rename a file into a subdirectory without specifying dest leaf'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.sftp.mkdir("potato")
        self.assertEquals(self.sftp.stat("testfile.txt").st_size, len(content_string))
        self.assertRaises(EnvironmentError, self.sftp.stat, "potato/testfile.txt")
        self.sftp.rename("testfile.txt", "potato")
        self.assertEquals(self.sftp.stat("potato/testfile.txt").st_size, len(content_string))
        self.assertRaises(EnvironmentError, self.sftp.stat, "testfile.txt")
        self.sftp.remove("potato/testfile.txt")
        self.sftp.rmdir("potato")

    def test_rename_file_into_root(self):
        '''rename a file into a subdirectory without specifying dest leaf'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertRaises(EnvironmentError, self.sftp.rename, "testfile.txt", "/testfile.txt")
        self.sftp.remove("testfile.txt")

    def test_rename_directory_into_file(self):
        '''rename a directory into a file - shouldn't work'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertRaises(EnvironmentError, self.sftp.rename, "/sftpcloudfs_testing", "testfile.txt")
        self.sftp.remove("testfile.txt")

    def test_rename_directory_into_directory(self):
        '''rename a directory into a directory'''
        self.sftp.mkdir("potato")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.sftp.rename("potato", "potato2")
        self.assertEquals(self.sftp.listdir("potato2"), [])
        self.sftp.rmdir("potato2")

    def test_rename_directory_into_existing_directory(self):
        '''rename a directory into an existing directory'''
        self.sftp.mkdir("potato")
        self.sftp.mkdir("potato2")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.assertEquals(self.sftp.listdir("potato2"), [])
        self.sftp.rename("potato", "potato2")
        self.assertEquals(self.sftp.listdir("potato2"), ["potato"])
        self.assertEquals(self.sftp.listdir("potato2/potato"), [])
        self.sftp.rmdir("potato2/potato")
        self.sftp.rmdir("potato2")

    def test_rename_directory_into_self(self):
        '''rename a directory into itself'''
        self.sftp.mkdir("potato")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.sftp.rename("potato", "/sftpcloudfs_testing")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.sftp.rename("potato", "/sftpcloudfs_testing/potato")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.sftp.rename("potato", "potato")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.sftp.rename("/sftpcloudfs_testing/potato", ".")
        self.assertEquals(self.sftp.listdir("potato"), [])
        self.sftp.rmdir("potato")

    def test_rename_full_directory(self):
        '''rename a directory into a directory'''
        self.sftp.mkdir("potato")
        self.create_file("potato/something.txt", "p")
        try:
            self.assertEquals(self.sftp.listdir("potato"), ["something.txt"])
            self.assertRaises(EnvironmentError, self.sftp.rename, "potato", "potato2")
        finally:
            self.sftp.remove("potato/something.txt")
            self.sftp.rmdir("potato")

    def test_rename_container(self):
        '''rename an empty container'''
        self.sftp.mkdir("/potato")
        self.assertEquals(self.sftp.listdir("/potato"), [])
        self.assertRaises(EnvironmentError, self.sftp.listdir, "/potato2")
        self.sftp.rename("/potato", "/potato2")
        self.assertRaises(EnvironmentError, self.sftp.listdir, "/potato")
        self.assertEquals(self.sftp.listdir("/potato2"), [])
        self.sftp.rmdir("/potato2")

    def test_rename_full_container(self):
        '''rename a full container'''
        self.sftp.mkdir("/potato")
        self.create_file("/potato/test.txt", "onion")
        self.assertEquals(self.sftp.listdir("/potato"), ["test.txt"])
        self.assertRaises(EnvironmentError, self.sftp.rename, "/potato", "/potato2")
        self.sftp.remove("/potato/test.txt")
        self.sftp.rmdir("/potato")

    def test_unicode_file(self):
        '''Test unicode file creation'''
        file_name = u"Smiley\u263a.txt"
        self.create_file(file_name, "Hello Moto")
        self.assertEqual(self.sftp.listdir(), [file_name])
        self.sftp.remove(file_name)

    def test_unicode_directory(self):
        '''Test unicode directory creation'''
        dir_name = u"Smiley\u263aDir"
        self.sftp.mkdir(dir_name)
        self.assertEqual(self.sftp.listdir(), [dir_name])
        self.sftp.rmdir(dir_name)

    def test_mkdir_container_unicode(self):
        ''' mkdir/chdir/rmdir directory '''
        directory = u"/Smiley\u263aContainer"
        self.sftp.mkdir(directory)
        self.sftp.chdir(directory)
        # FIXME shouldn't have to utf-8 decode here?
        self.assertEqual(self.sftp.getcwd().decode("utf-8"), directory)
        self.sftp.chdir("..")
        self.sftp.rmdir(directory)

    def test_fakedir(self):
        '''Make some fake directories and test'''

        obj1 = self.container.create_object("test1.txt")
        obj1.content_type = "text/plain"
        obj1.write("Hello Moto")

        obj2 = self.container.create_object("potato/test2.txt")
        obj2.content_type = "text/plain"
        obj2.write("Hello Moto")

        obj3 = self.container.create_object("potato/sausage/test3.txt")
        obj3.content_type = "text/plain"
        obj3.write("Hello Moto")

        obj4 = self.container.create_object("potato/sausage/test4.txt")
        obj4.content_type = "text/plain"
        obj4.write("Hello Moto")

        self.assertEqual(self.sftp.listdir(), ["potato", "test1.txt"])
        self.assertEqual(self.sftp.listdir("potato"), ["sausage","test2.txt"])
        self.assertEqual(self.sftp.listdir("potato/sausage"), ["test3.txt", "test4.txt"])

        self.sftp.chdir("potato")

        self.assertEqual(self.sftp.listdir(), ["sausage","test2.txt"])
        self.assertEqual(self.sftp.listdir("sausage"), ["test3.txt", "test4.txt"])

        self.sftp.chdir("sausage")

        self.assertEqual(self.sftp.listdir(), ["test3.txt", "test4.txt"])

        self.sftp.chdir("../..")

        self.container.delete_object(obj1.name)
        self.container.delete_object(obj2.name)
        self.container.delete_object(obj3.name)
        self.container.delete_object(obj4.name)

        self.assertEqual(self.sftp.listdir(), [])

    def tearDown(self):
        # Delete eveything from the container using the API
        fails = self.container.list_objects()
        for obj in fails:
            self.container.delete_object(obj)
        self.sftp.rmdir("/sftpcloudfs_testing")
        self.sftp.close()
        self.transport.close()
        self.assertEquals(fails, [], "The test failed to clean up after itself leaving these objects: %r" % fails)

if __name__ == '__main__':
    unittest.main()
