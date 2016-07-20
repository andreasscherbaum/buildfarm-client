#!/usr/bin/env python
#
# Installation tests (for PostgreSQL)
#
# written by: Andreas Scherbaum <ascherbaum@pivotal.io>
#             Andreas Scherbaum <ads@pgug.de>
#

import os
import sys
import logging


# start with the assumption that everything is ok
error = False


logging.getLogger().setLevel(logging.INFO)

if sys.version_info[0] < 3:
    sys_modules = [ 're', 'tempfile', 'atexit', 'shutil', 'time', 'subprocess', 'socket', 'sqlite3', 'time', 'argparse', 'yaml', 'hashlib', 'string', 'urllib2', 'StringIO', 'gzip', 'zlib', 'datetime', 'copy', 'glob', 'shlex', 'stat', 'lockfile' ]
else:
    sys_modules = [ 're', 'tempfile', 'atexit', 'shutil', 'time', 'subprocess', 'socket', 'sqlite3', 'time', 'argparse', 'yaml', 'hashlib', 'string', 'urllib3', 'io', 'gzip', 'zlib', 'datetime', 'copy', 'glob', 'shlex', 'stat', 'lockfile' ]

for module in sys_modules:
    logging.debug("try to import module: " + module)
    try:
        __import__(module)
    except ImportError:
        logging.error("failed to load module: " + module)
        error = True

# urlparse is different in Python 2 and 3
logging.debug("try to import module: urlparse / urljoin")
try:
    from urlparse import urljoin # Python2
except ImportError:
    try:
        from urllib.parse import urljoin # Python3
    except ImportError:
        logging.error("failed to load module: urlparse / urljoin")
        error = True


# try private modules
logging.debug("try to import private module: Config")
try:
    from config import Config
except ImportError:
    logging.error("failed to load private module: Config")
    error = True

logging.debug("try to import private module: Repository")
try:
    from repository import Repository
except ImportError:
    logging.error("failed to load private module: Repository")
    error = True

logging.debug("try to import private module: Build")
try:
    from build import Build
except ImportError:
    logging.error("failed to load private module: Build")
    error = True

logging.debug("try to import private module: Patch")
try:
    from patch import Patch
except ImportError:
    logging.error("failed to load private module: Patch")
    error = True

logging.debug("try to import private module: Database")
try:
    from database import Database
except ImportError:
    logging.error("failed to load private module: Database")
    error = True

logging.debug("try to import private module: Buildfarm")
try:
    from buildfarm import Buildfarm
except ImportError:
    logging.error("failed to load private module: Buildfarm")
    error = True



# load config file if one is specified
if (len(sys.argv) >= 3 and sys.argv[1] == '-c' and len(sys.argv[2]) > 0):
    logging.debug("load config")
    try:
        config = Config()
        config.config_help(False)
        config.parse_parameters()
        config.load_config()
        config.build_and_verify_config()
    except:
        error = True
else:
    # require "-c <config file>" because the Config module loads a config this way - reuse the code
    print("")
    print("Please specify a config file with:  -c <config file>")
    print("")
    error = True



if (error is True):
    print("")
    print("Please verify your installation!")
    print("")
else:
    print("")
    print("Everything seems to be OK")
    print("")

