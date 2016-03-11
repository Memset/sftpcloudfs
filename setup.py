#!/usr/bin/env python
from setuptools import setup, find_packages
from sftpcloudfs.constants import version, project_url

def readme():
    try:
        return open('README.md').read()
    except:
        return ""

setup(name='sftp-cloudfs',
      version=version,
      description='SFTP interface to OpenStack Object Storage (Swift)',
      long_description=readme(),
      author='Nick Craig-Wood',
      author_email='nick@memset.com',
      url=project_url,
      license='MIT',
      include_package_data=True,
      zip_safe=False,
      install_requires=['paramiko>=1.7.6', 'python-swiftclient>=2.0.0', 'python-daemon>=1.5',
                        'python-memcached>=1.45', 'ftp-cloudfs>=0.35'],
      scripts=['bin/sftpcloudfs'],
      packages = find_packages(exclude=['tests']),
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
