import os
import shutil
import pysftp
import logging

logger = logging.getLogger(__name__)


def download_sftp(
    host, username, password, sftp_filepath, local_filepath, local_filepath_archive
):
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    with pysftp.Connection(
        host=host, username=username, password=password, cnopts=cnopts
    ) as sftp_con:
        logger.info(f"@102 - Connected to {host}")

        with sftp_con.cd(sftp_filepath):
            logger.info(f"@103 - Go to sftp dir: {sftp_filepath}")

            for file in sftp_con.listdir():
                lstatout = str(sftp_con.lstat(file)).split()[0]

                if "d" not in lstatout:  # If file
                    logger.info(f"@104 - downloading: {file}")
                    sftp_con.get(sftp_filepath + file, local_filepath + file)
                    sftp_file_size = sftp_con.lstat(sftp_filepath + file).st_size
                    local_file_size = os.stat(local_filepath + file).st_size

                    if sftp_file_size == local_file_size:  # Check file size
                        logger.info(f"@105 - Download success: {file}")
                        sftp_con.remove(sftp_filepath + file)  # Delete file from remote

        sftp_con.close()


def upload_sftp(
    host,
    username,
    password,
    sftp_filepath,
    local_filepath,
    local_filepath_archive,
    filename,
):
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    with pysftp.Connection(
        host=host, username=username, password=password, cnopts=cnopts
    ) as sftp_con:
        logger.info(f"@202 - Connected to {host}")
        with sftp_con.cd(sftp_filepath):
            logger.info(f"@203 - Go to sftp dir: {sftp_filepath}")
            sftp_con.put(local_filepath + filename)
            sftp_file_size = sftp_con.lstat(sftp_filepath + filename).st_size
            local_file_size = os.stat(local_filepath + filename).st_size

            if sftp_file_size == local_file_size:
                logger.info("@204 - Uploaded successfully!")
                if not os.path.exists(local_filepath_archive):
                    os.makedirs(local_filepath_archive)

                shutil.move(
                    local_filepath + filename, local_filepath_archive + filename
                )
                logger.info(f"@209 Moved file: {filename}")

        sftp_con.close()
