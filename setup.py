#!/usr/bin/env python
from setuptools import setup, find_packages
from sftpcloudfs import version, project_url

setup(name='sftpd-cloudfs',
      version=version,
      description='SFTP interface to Rackspace Cloud Files and Open Stack Object Storage (Swift)',
      author='Nick Craig-Wood',
      author_email='nick@memset.com',
      url=project_url,
      license='MIT',
      include_package_data=True,
      zip_safe=False,
      install_requires=['python-paramiko', 'python-cloudfiles', 'python-daemon',
                        'python-ftp-cloudfs'],
      scripts=['bin/sftpcloudfs'],
      packages = find_packages(exclude=['tests', 'debian']),
      tests_require = ["nose"],
      classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Programming Language :: Python',
        'Operating System :: OS Independent',
        'Environment :: No Input/Output (Daemon)',
        'License :: OSI Approved :: MIT License',
        ],
      test_suite = "nose.collector",
      )
