#!/usr/bin/env python
#
# Collect system and build information for support
#
# written by: Andreas Scherbaum <ascherbaum@pivotal.io>
#
# History:
#  v0.1 - 2015-01-13: commandline parameters
#  v0.2 - 2015-01-21: database connect, gather table dumps
#  v0.3 - 2015-02-02: rewrote formatter for table dumps
#  v0.4 - 2015-02-05: add system information
#  v0.5 - 2015-02-10: add pg_dump of the database schema
#  v0.6 - 2015-11-15: remove database support
#                     add build information support
#  v0.7 - 2016-02-22: add logfiles from buildfarm client



import re
import os
import sys
import argparse
import logging
import tempfile
import atexit
import shutil
import subprocess
from subprocess import Popen
import socket
from time import gmtime, localtime, strftime
import glob



# start with 'info', can be overriden by '-q' later on
logging.basicConfig(level = logging.INFO,
		    format = '%(levelname)s: %(message)s')


# exit_handler()
#
# exit handler, called upon exit of the script
# main job: remove the temp directory
#
# parameters:
#  none
# return:
#  none
def exit_handler():
    if ('sp_dir' in globals()):
        global sp_dir
        if (os.path.isdir(sp_dir) is True and len(sp_dir) > 1):
            logging.info("temp directory exists, removing it ...")
            shutil.rmtree(sp_dir)

# register exit handler
atexit.register(exit_handler)



# find_system_path()
#
# find an executable in system path
#
# parameters:
#  - executable name
# return:
#  - full path, or None
def find_system_path(exe):
    dir = ['/sbin', '/usr/sbin', '/bin', '/usr/bin', '/usr/local/bin']
    for entry in dir:
        t = os.path.join(entry, exe)
        if (os.path.isfile(t) and os.access(t, os.X_OK)):
	    return t
	t = t + '.exe'
        if (os.path.isfile(t) and os.access(t, os.X_OK)):
	    return t
    return None



# write_parameters()
#
# dump parameters into support archive
#
# parameters:
#  - temp directory
#  - array with arguments (after parsing)
# return:
#  none
def write_parameters(dir, args):
    f = open(os.path.join(dir, 'script_parameters.txt'), 'w')
    f.write('quiet: ' + str(args.quiet) + os.linesep)
    f.write('archive_type: ' + str(args.archive_type) + os.linesep)
    f.write('archive_name: ' + str(args.archive_name) + os.linesep)
    f.close()



# dump_lsb_release()
#
# dump LSB (Linux Standard Base) information into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_lsb_release(dir):
    e = find_system_path('lsb_release')
    if (e is None):
        logging.info("no 'lsb_release' executable found")
        return

    null_file = open(os.devnull, 'w')
    o = subprocess.check_output([e, '-a'], stderr=null_file)
    null_file.close()
    f = open(os.path.join(dir, 'lsb_release.txt'), 'w')
    f.write(o)
    f.close()



# dump_sysctl()
#
# dump current sysctl settings into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_sysctl(dir):
    e = find_system_path('sysctl')
    if (e is None):
        logging.info("no 'sysctl' executable found")
        return

    # use '-a' instead of '-a--', because Mac OS X does only understand the short options
    o = subprocess.check_output([e, '-a'])
    f = open(os.path.join(dir, 'sysctl.txt'), 'w')
    f.write(o)
    f.close()



# dump_python_version()
#
# dump Python information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_python_version(dir):
    o = subprocess.check_output([sys.executable, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'python_version.txt'), 'w')
    f.write(sys.executable + os.linesep)
    f.write(o)
    f.close()



# dump_perl_version()
#
# dump Perl information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_perl_version(dir):
    e = find_system_path('perl')
    if (e is None):
        logging.info("no 'perl' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'perl_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_gcc_version()
#
# dump gcc information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_gcc_version(dir):
    e = find_system_path('gcc')
    if (e is None):
        logging.info("no 'gcc' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'gcc_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_gpp_version()
#
# dump gpp information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_gpp_version(dir):
    e = find_system_path('c++')
    if (e is None):
        logging.info("no 'c++' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'gpp_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_ccache_version()
#
# dump ccache information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_ccache_version(dir):
    e = find_system_path('ccache')
    if (e is None):
        logging.info("no 'ccache' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'ccache_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_bison_version()
#
# dump bison information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_bison_version(dir):
    e = find_system_path('bison')
    if (e is None):
        logging.info("no 'bison' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'bison_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_yacc_version()
#
# dump yacc information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_yacc_version(dir):
    e = find_system_path('yacc')
    if (e is None):
        logging.info("no 'yacc' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'yacc_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_flex_version()
#
# dump flex information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_flex_version(dir):
    e = find_system_path('flex')
    if (e is None):
        logging.info("no 'flex' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'flex_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_make_version()
#
# dump make information (executable, version) into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_make_version(dir):
    e = find_system_path('make')
    if (e is None):
        logging.info("no 'make' executable found")
        return

    o = subprocess.check_output([e, '--version'], stderr=subprocess.STDOUT)
    f = open(os.path.join(dir, 'make_version.txt'), 'w')
    f.write(e + os.linesep)
    f.write(o)
    f.close()



# dump_hostname()
#
# dump hostname into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_hostname(dir):
    f = open(os.path.join(dir, 'hostname.txt'), 'w')
    f.write(socket.gethostname() + os.linesep)
    f.write(socket.getfqdn() + os.linesep)
    f.close()



# dump_time()
#
# dump time and timezone into support archive
#
# parameters:
#  - temp directory
# return:
#  none
def dump_time(dir):
    f = open(os.path.join(dir, 'timestamp.txt'), 'w')
    f.write(strftime("%Y-%m-%d %H:%M:%S %Z", localtime()) + os.linesep)
    f.close()



# parse_parameters()
#
# parse commandline parameters, fill in array with arguments
#
# parameters:
#  none
# return:
#  list with: parser, arguments
def parse_parameters():
    parser = argparse.ArgumentParser(description = 'Extract system and build debugging information',
				     epilog = 'For questions, please contact Pivotal Support',
				     add_help = False)
    parser.add_argument('-q', '--quiet', default = False, dest = 'quiet', action='store_true', help = 'run quietly')
    parser.add_argument('--archive-type', default = 'zip', dest = 'archive_type', choices = ['zip', 'tar'], help = 'choose archive type')
    parser.add_argument('--archive-name', default = '', dest = 'archive_name', help = 'choose archive file name (default: autogenerated)')
    parser.add_argument('-l', '--logfiles', default = '', dest = 'logfiles', help = 'directory with extra logfiles to include')

    # parse parameters
    args = parser.parse_args()

    if (args.quiet is True):
        logging.getLogger().setLevel(logging.ERROR)

    # verify that this is indeed a PostgreSQL or Greenplum build directory
    if (is_postgresql() is False and is_greenplum() is False):
        parser.print_help()
        print("")
        print("Error: current directory is not a PostgreSQL or Greenplum source directory")
        sys.exit(1)


    if (platform() == 'unsupported'):
        print("")
        print("Error: this platform is not supported")
        sys.exit(1)


    e = find_system_path('sysctl')
    if (e is None):
        logging.info("no 'sysctl' executable found")
        return



    #if (args.archive_name == ''):
    #    os_archive_name = tempfile.mkstemp(suffix = '.' + args.archive_type)
    #    args.archive_name = os_archive_name[1]
    #    logging.info('Random archive name generated: ' + args.archive_name)


    return [parser, args]



def is_greenplum():
    # verify if it is a Greenplum repository
    files = ['README.PostgreSQL', 'GNUmakefile.in', 'getversion', 'putversion', 'README.debian', 'LICENSE', 'COPYRIGHT']
    missing_files = False
    for file in files:
        if not (os.path.isfile(file)):
            missing_files = True
    if (missing_files is False):
        # seems to be a Greenplum repository
        return True

    # verify if it is an internal Greenplum repository
    files = ['README.postgresql', 'GNUmakefile.in', 'getversion', 'putversion', 'LICENSE', 'COPYRIGHT']
    missing_files = False
    for file in files:
        if not (os.path.isfile(file)):
            missing_files = True
    if (missing_files is False):
        # seems to be a Greenplum repository
        return True

    return False



def is_postgresql():
    # verify if it is a PostgreSQL repository
    files = ['README.git', 'GNUmakefile.in', 'HISTORY', 'COPYRIGHT']
    missing_files = False
    for file in files:
        if not (os.path.isfile(file)):
            missing_files = True
    if (missing_files is False):
        # seems to be a PostgreSQL repository
        return True
    return False



# zipdir()
#
# pack a directory into a zip file
#
# parameters:
#  - directory
#  - zip handle
# return:
#  none
def zipdir(path, zip):
    for root, dirs, files in os.walk(path):
        for file in files:
            zip.write(os.path.join(root, file))



# dump_gp_version()
#
# copy the 'VERSION' file into the support package
#
# parameters:
#  - temp directory
# return:
#  none
def dump_gp_version(dir):
    # only exists in Greenplum
    if (os.path.isfile('VERSION')):
        shutil.copyfile('VERSION', os.path.join(dir, 'VERSION'))



# dump_build_logs()
#
# copy the 'config.log' and 'config.status' files into the support package
#
# parameters:
#  - temp directory
# return:
#  none
def dump_build_logs(dir):
    files = ['config.log', 'config.status', 'buildclient-config.txt', 'repository-info.txt',
             'src/test/regress/regression.diffs', 'src/test/regress/regression.out']
    files_log = glob.glob('log_*.txt')
    files.extend(files_log)
    # there might be a diff file with the sum of all applied patches
    files.append(str(os.getcwd()) + '.diff')

    for filename in files:
        if (os.path.isfile(filename)):
            # copy the file, with the original filename
            shutil.copyfile(filename, os.path.join(dir, os.path.basename(filename)))



# include_extra_logs()
#
# copy all files from a specified directory into the archive
#
# parameters:
#  - extra directory
#  - temp directory
# return:
#  none
def include_extra_logs(extra, dir):
    files = []
    files_log = glob.glob(extra + os.sep + '*')
    files.extend(files_log)

    for filename in files:
        if (os.path.isfile(filename)):
            # copy the file, with the original filename
            shutil.copyfile(filename, os.path.join(dir, os.path.basename(filename)))



# dump_platform()
#
# copy the platform into the support package
#
# parameters:
#  - temp directory
# return:
#  none
def dump_platform(dir):
    f = open(os.path.join(dir, 'platform.txt'), 'w')
    f.write(str(platform()) + os.linesep)
    f.close()



# platform()
#
# identify the current operating system
#
# parameters:
#  none
# return:
#  - operating system string
def platform():
    if sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform.startswith('darwin'):
        return 'mac'
    return 'unsupported'



# from: http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
# human_size()
#
# format number into human readable output
#
# parameters:
#  - number
# return:
#  - string with formatted number
def human_size(size_bytes):
    """
    format a size in bytes into a 'human' file size, e.g. bytes, KB, MB, GB, TB, PB
    Note that bytes/KB will be reported in whole numbers but MB and above will have greater precision
    e.g. 1 byte, 43 bytes, 443 KB, 4.3 MB, 4.43 GB, etc
    """
    if (size_bytes == 1):
        # because I really hate unnecessary plurals
        return "1 byte"

    suffixes_table = [('bytes',0),('KB',0),('MB',1),('GB',2),('TB',2), ('PB',2)]

    num = float(size_bytes)
    for suffix, precision in suffixes_table:
        if (num < 1024.0):
            break
        num /= 1024.0

    if (precision == 0):
        formatted_size = "%d" % num
    else:
        formatted_size = str(round(num, ndigits=precision))

    return "%s %s" % (formatted_size, suffix)






# main code

args = parse_parameters()
args_parser = args[0]
args = args[1]



# what we need:
#
# * basic Python info
# * OS version
# * OS sysctl
# * hostname
# * GP version
# * platform
# * config.log


# generate a temp directory
sp_dir = tempfile.mkdtemp()
sp_dir_name = os.path.basename(os.path.normpath(sp_dir))
logging.info("temporary directory: " + sp_dir + " (name: " + sp_dir_name + ")")


# dump parameters into file
write_parameters(sp_dir, args)


# dump system info
logging.info("dump system information")
dump_time(sp_dir)
dump_python_version(sp_dir)
dump_perl_version(sp_dir)
dump_gcc_version(sp_dir)
dump_gpp_version(sp_dir)
dump_ccache_version(sp_dir)
dump_bison_version(sp_dir)
dump_yacc_version(sp_dir)
dump_flex_version(sp_dir)
dump_make_version(sp_dir)
dump_lsb_release(sp_dir)
dump_sysctl(sp_dir)
dump_hostname(sp_dir)
dump_gp_version(sp_dir)
dump_platform(sp_dir)
dump_build_logs(sp_dir)
if (os.path.isdir(args.logfiles)):
    include_extra_logs(args.logfiles, sp_dir)


for (dirpath, dirnames, filenames) in os.walk(sp_dir):
    logging.info('files in support package:')
    logging.info(sorted(filenames, key=str.lower))
    break


# pack final archive
if (args.archive_name == ''):
    os_archive_name = tempfile.mkstemp(suffix = '.' + args.archive_type)
    args.archive_name = os_archive_name[1]
    if (args.archive_type == 'tar'):
        args.archive_name = args.archive_name + '.gz'
    logging.info('random archive name generated: ' + args.archive_name)

logging.info("creating archive (type: {0}): {1}".format(args.archive_type, args.archive_name))
if (args.archive_type == 'zip'):
    import zipfile
    try:
        import zlib
        compression = zipfile.ZIP_DEFLATED
        logging.info('type is zip, compression is enabled')
    except:
        compression = zipfile.ZIP_STORED
        logging.info('type is zip, compression is disabled')

    zipf = zipfile.ZipFile(args.archive_name, 'w')
    # join into the temp dir
    os.chdir(sp_dir)
    os.chdir('..')
    # and only pack this directory, exclude the full temp pathname
    zipdir(sp_dir_name, zipf)
    zipf.close()

if (args.archive_type == 'tar'):
    import tarfile
    tarf = tarfile.open(args.archive_name, 'w:gz')
    tarf.add(sp_dir, arcname = sp_dir_name)
    tarf.close()


file_size = os.stat(args.archive_name).st_size
print("")
print("Your log archive is ready: " + args.archive_name)
print("Size: " + human_size(file_size))
print("")
