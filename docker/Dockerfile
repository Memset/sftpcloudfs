FROM python:2.7
MAINTAINER Juan J. Martinez <jjm@usebox.net>

LABEL version="1.0"
LABEL description="This image runs a sftpcloudfs SFTP proxy to OpenStack Object Storage (swift)."

RUN apt-get update && apt-get install -y memcached
RUN pip install paramiko==1.17.0 sftp-cloudfs python-keystoneclient
RUN useradd -M -d /nonexistent -s /bin/false sftpcloudfs

ADD sftpcloudfs.conf /config/
ADD run-sftpcloudfs /usr/bin/

RUN chown -R sftpcloudfs:sftpcloudfs /config/

ENV AUTH https://your-auth-service/1.0
ENV PORT 8022

EXPOSE $PORT
VOLUME /config/
ENTRYPOINT exec /usr/bin/run-sftpcloudfs

