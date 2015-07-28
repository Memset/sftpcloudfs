First pull the image with:

    docker pull jjmartinez/sftpcloudfs

You can run the SFTP server with:

    docker run --env AUTH=YOURAUTH -d --name sftp -p 8022:8022 jjmartinez/sftpcloudfs

Replace `YOURAUTH` with the public authentication service of your Swift provider (eg. https://auth.storage.memset.com/v1.0).

Other ENV variables are:

 - PORT: port to listen for connections (default: 8022).

For further configuration you can mount `/config/` volume and copy the following files:

 - Your own `sftpcloudfs.conf` file (eg. for Keystone 2.0 auth).
 - An existing `id_rsa` key (by default a new one will be created when the container is run).

Building the container
----------------------

Just run:

    docker build .

