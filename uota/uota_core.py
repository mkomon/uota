"""
Update firmware written in MicroPython over the air.

MIT license; Copyright (c) 2021 Martin Komon
"""

import gc
import uos
import urequests
import uzlib
import utarfile as tarfile
from micropython import const

try:
    import logging
    log = logging.getLogger(__name__)
except ImportError:
    class logging:
        def critical(self, entry):
            print('CRITICAL: ' + entry)
        def error(self, entry):
            print('ERROR: ' + entry)
        def warning(self, entry):
            print('WARNING: ' + entry)
        def info(self, entry):
            print('INFO: ' + entry)
        def debug(self, entry):
            print('DEBUG: ' + entry)
    log = logging()
            
try:
    from ucertpin import get_pubkey_hash_from_der
    ucertpin_available = True
except ImportError:
    log.warning('ucertpin package not found, certificate pinning is disabled')
    ucertpin_available = False


GZDICT_SZ = const(31)
ota_config = {}

def load_ota_cfg():
    try:
        with open('uota.cfg', 'r') as f:
            ota_config.update(eval(f.read()))
        return True
    except OSError:
        log.error('Cannot find uota config file `uota.cfg`. OTA is disabled.')
        return False

def recursive_delete(path: str):
    """
    Delete a directory recursively, removing files from all sub-directories before
    finally removing empty directory. Works for both files and directories.

    No limit to the depth of recursion, will fail on too deep dir structures.
    """
    # prevent deleting the whole filesystem and skip non-existent files
    if not path or not uos.stat(path):
        return

    path = path[:-1] if path.endswith('/') else path

    try:
        children = uos.listdir(path)
        # no exception thrown, this is a directory
        for child in children:
            recursive_delete(path + '/' + child)
    except OSError:
        uos.remove(path)
        return
    uos.rmdir(path)


def check_free_space(min_free_space: int) -> bool:
    """
    Check available free space in filesystem and return True/False if there is enough free space
    or not.

    min_free_space is measured in kB
    """
    if not any([isinstance(min_free_space, int), isinstance(min_free_space, float)]):
        log.warning('min_free_space must be an int or float')
        return False

    fs_stat = uos.statvfs('/')
    block_sz = fs_stat[0]
    free_blocks = fs_stat[3]
    free_kb = block_sz * free_blocks / 1024
    return free_kb >= min_free_space


def check_for_updates(version_check=True, quiet=False, pubkey_hash=b'') -> bool:
    """
    Check for available updates, download new firmware if available and return True/False whether
    it's ready to be installed, there is enough free space and file hash matches.
    """
    gc.collect()

    if not load_ota_cfg():
        return False

    if not ota_config['url'].endswith('/'):
        ota_config['url'] = ota_config['url'] + '/'

    response = urequests.get(ota_config['url'] + 'latest')

    if ucertpin_available and pubkey_hash:
        server_pubkey_hash = get_pubkey_hash_from_der(response.raw.getpeercert(True))
        if server_pubkey_hash != pubkey_hash:
            log.warning('Certificate pinning failed, the hash of server public key does not match. Aborting the update.')
            return False

    remote_version, remote_filename, *optional = response.text.strip().rstrip(';').split(';')
    min_free_space, *remote_hash = optional if optional else (0, '')
    min_free_space = int(min_free_space)
    remote_hash = remote_hash[0] if remote_hash else ''

    try:
        with open('version', 'r') as f:
            local_version = f.read().strip()
    except OSError:
        if version_check:
            not quiet and log.warning('local version information missing, cannot proceed')
            return False
        not quiet and log.warning('local version information missing, ignoring it')

    if not version_check or remote_version > local_version:
        not quiet and log.info(f'new version {remote_version} is available')
        if not check_free_space(min_free_space):
            not quiet and log.error('not enough free space for the new firmware')
            return False

        if remote_hash:
            import uhashlib
            import ubinascii
            hash_obj = uhashlib.sha256()

        response = urequests.get(ota_config['url'] + remote_filename)
        with open(ota_config['tmp_filename'], 'wb') as f:
            while True:
                chunk = response.raw.read(512)
                if not chunk:
                    break
                if remote_hash:
                    hash_obj.update(chunk)
                f.write(chunk)
        if remote_hash and ubinascii.hexlify(hash_obj.digest()).decode() != remote_hash:
            not quiet and log.error('hashes don\'t match, cannot install the new firmware')
            uos.remove(ota_config['tmp_filename'])
            return False
        return True

    return False

def install_new_firmware(quiet=False):
    """
    Unpack new firmware that is already downloaded and perform a post-installation cleanup.
    """
    gc.collect()

    if not load_ota_cfg():
        return

    try:
        uos.stat(ota_config['tmp_filename'])
    except OSError:
        log.info('No new firmware file found in flash.')
        return

    with open(ota_config['tmp_filename'], 'rb') as f1:
        f2 = uzlib.DecompIO(f1, GZDICT_SZ)
        f3 = tarfile.TarFile(fileobj=f2)
        for _file in f3:
            file_name = _file.name
            if file_name in ota_config['excluded_files']:
                item_type = 'directory' if file_name.endswith('/') else 'file'
                not quiet and log.info(f'Skipping excluded {item_type} {file_name}')
                continue

            if file_name.endswith('/'):  # is a directory
                try:
                    not quiet and log.debug(f'creating directory {file_name} ... ')
                    uos.mkdir(file_name[:-1])  # without trailing slash or fail with errno 2
                    not quiet and log.debug('ok')
                except OSError as e:
                    if e.errno == 17:
                        not quiet and log.debug('already exists')
                    else:
                        raise e
                continue
            file_obj = f3.extractfile(_file)
            with open(file_name, 'wb') as f_out:
                written_bytes = 0
                while True:
                    buf = file_obj.read(512)
                    if not buf:
                        break
                    written_bytes += f_out.write(buf)
                not quiet and log.info(f'file {file_name} ({written_bytes} B) written to flash')

    uos.remove(ota_config['tmp_filename'])
    if load_ota_cfg():
        for filename in ota_config['delete']:
            recursive_delete(filename)

