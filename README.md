# uOTA - OTA updater for MicroPython

## Overview

Update your device firmware written in MicroPython over the air. Suitable for private and/or larger projects with many files.

Requires MicroPython 1.17 or newer.

## How it's different from other OTA Updaters

Other OTA updaters, notably [rdehuyss/micropython-ota-updater](https://github.com/rdehuyss/micropython-ota-updater), [smysnk/micropython-ota-updater](https://github.com/smysnk/micropython-ota-updater) and [RangerDigital/senko](https://github.com/RangerDigital/senko), update code from a particular branch on GitHub. This OTA is different in the following aspects:

- update from any HTTP(S) server with no hardcoded endpoints, allowing you to keep control of your hosting without dependencies
- no need for GitHub account
- no need to make your code public or pay for private repos
- replaces files in-place without storing uncompressed new firmware in flash
- replaces files in the root of the filesystem
- downloads new firmware as a single compressed .tar.gz file which is more efficient for a larger number of files
- compares SHA256 hash of the new firmware file but not of individual files (optional)
- checks if there is sufficient available free space in the file system (optional)
- compares firmware version: the content of `version` file from MicroPython device file system and the version published on your server stored in `latest` file, see details below

## Installation (requires MicroPython release 1.20)

Install using [MicroPython mip](https://docs.micropython.org/en/latest/reference/packages.html)

```python
>>> import mip
>>> mip.install('github:mkomon/uota')
```

or using mpremote

```python
mpremote mip install github:mkomon/uota
```

## Manual Installation

Copy uota.py to the root directory or "lib" directory of your device.

## Usage

Drop the following files into the root of your project:

1. uota.cfg
   - must be a valid Python dictionary with the following keys:
      - `url`
         - base HTTP or HTTPS URL where to look for new firmware
         - ends with a trailing slash
      - `tmp_filename`
         - the new firmware will be stored in a file of this name
         - this file is deleted automatically after 
      - `excluded_files`
         - files or directories with matching names will be skipped and not overwritten with new versions. Keep local device configuration such as wifi credentials or certificates from being overwritten.
      - `delete`
        - items are file/directory names as strings, these will be deleted after new firmware is installed
        - this configuration option is loaded after the new firmware is installed to perform any cleanup that may be needed
1. `version`
    - the current version of the firmware
    - version check can be disabled by passing `version_check=False` argument to `uota.check_for_updates()`

Publish new firmware on your HTTP(S) server as two files:

- firmware file of any name
  - a TAR file compressed with gzip, the content will be downloaded and unpacked directly into the root of the filesystem of your MicroPython device
  - can be created with `tar -czf firmware.tar.gz *` shell command on any Linux/UNIX/MacOS system
- `latest`
  - a text file with the following fields separated by a semicolon:
    - version
    - new firmware filename available on the server
    - required amount of additional free space in flash, measured in kB (optional)
    - SHA256 hash of the new firmware file (optional, but makes the previous item mandatory)
  - valid examples:
    - 2.0.1;firmware.tar.gz
    - 2.0.1;firmware.tar.gz;2
    - 2.0.1;firmware.tar.gz;0;8870f8b3bd8b54437f0a7f721cd3f3fe208e60638dcf36a9f4efe31dab58c548
  - invalid examples:
    - firmware.tar.gz
    - 2.0.1;firmware.tar.gz;8870f8b3bd8b54437f0a7f721cd3f3fe208e60638dcf36a9f4efe31dab58c548

And then use `uota` in your project as follows. You must connect to wifi yourself as `uota` expects a working wifi connection to function.

```python
import uota
import machine
...
from connect_wifi import connect_wifi
connect_wifi()
...
if do_ota_update and uota.check_for_updates():
      uota.install_new_firmware()
      machine.reset()
```

### SSL security considerations

MicroPython's built-in SSL package does not support checking server certificate or authenticating the client with the server using certificates. uOTA can perform certificate pinning by checking the hash of server-side private key, if [ucertpin](https://github.com/mkomon/ucertpin) is installed.

#### Certificate pinning

Certificate pinning is disabled by default. To enable it make [ucertpin](https://github.com/mkomon/ucertpin) available for import and pass `pubkey_hash=b'---your-SHA256-hash-value---'` argument to `uota.check_for_updates`:

```python
>>> import uota
>>> uota.check_for_updates()     # no certificate pinning
new version 0.3 is available
True
>>> uota.check_for_updates(pubkey_hash=b'abc')    # certificate pinning with incorrect hash
Certificate pinning failed, the hash of server public key does not match. Aborting the update.
False
```
