import re
import os
import sys
import shutil
import subprocess
import argparse
import yaml
import logging
import hashlib
import string
import atexit
from lockfile import LockFile, LockTimeout
from subprocess import Popen
from distutils.version import LooseVersion
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf8')


class Config:

    def __init__(self):
        self.__cmdline_read = 0
        self.__configfile_read = 0
        self.__fully_initiated = 0
        self.arguments = False
        self.argument_parser = False
        self.configfile = False
        self.config = False
        self.output_help = True
        self.lockfile_handle = False
        self.lockfile_name = False

        if (os.environ.get('HOME') is None):
            logging.error("$HOME is not set!")
            sys.exit(1)
        if (os.path.isdir(os.environ.get('HOME')) is False):
            logging.error("$HOME does not point to a directory!")
            sys.exit(1)

        atexit.register(self.exit_handler)



    def exit_handler(self):
        if (self.__fully_initiated == 1 and self.lockfile_name is not False):
            if (hasattr(self.lockfile_handle, 'release') is True):
                self.lockfile_handle.release()
                logging.debug("lock on " + self.lockfile_name + " released")



    # config_help()
    #
    # flag if help shall be printed
    #
    # parameter:
    #  - self
    #  - True/False
    # return:
    #  none
    def config_help(self, config):
        if (config is False or config is True):
            self.output_help = config
        else:
            print("")
            print("invalid setting for config_help()")
            sys.exit(1)



    # print_help()
    #
    # print the help
    #
    # parameter:
    #  - self
    # return:
    #  none
    def print_help(self):
        if (self.output_help is True):
            self.argument_parser.print_help()



    # parse_parameters()
    #
    # parse commandline parameters, fill in array with arguments
    #
    # parameter:
    #  - self
    # return:
    #  none
    def parse_parameters(self):
        parser = argparse.ArgumentParser(description = 'PostgreSQL & Greenplum Buildfarm Client',
                                         epilog = 'For questions, please see http://greenplum.org/',
                                         add_help = False)
        self.argument_parser = parser
        parser.add_argument('--help', default = False, dest = 'help', action = 'store_true', help = 'show this help')
        parser.add_argument('-c', '--config', default = '', dest = 'config', help = 'configuration file')
        parser.add_argument('--animal', default = '', dest = 'animal', help = 'build farm animal name')
        parser.add_argument('--secret', default = '', dest = 'secret', help = 'build farm animal secret')
        parser.add_argument('--source', default = '', dest = 'source', help = 'path/URL to git repository')
        parser.add_argument('--target', default = '', dest = 'target', help = 'URL to build farm server')
        parser.add_argument('--cache-dir', default = '', dest = 'cache_dir', help = 'path to cache directory for git clone')
        parser.add_argument('--build-dir', default = '', dest = 'build_dir', help = 'path to build directory for build')
        parser.add_argument('--install-dir', default = '', dest = 'install_dir', help = 'path to install directory for tests')
        parser.add_argument('--git-bin', default = '', dest = 'git_bin', help = 'git binary, default: search in $PATH')
        parser.add_argument('--git-depth', default = '', dest = 'git_depth', help = 'depth for a shallow git clode, default: everything')
        parser.add_argument('--ccache-bin', default = '', dest = 'ccache_bin', help = 'compiler cache binary, default: none')
        # store_true: store "True" if specified, otherwise store "False"
        # store_false: store "False" if specified, otherwise store "True"
        parser.add_argument('--no-clean-on-failure', default = True, dest = 'clean_on_failure', action = 'store_false', help = 'do not clean up the build dir if there was an error')
        parser.add_argument('--no-clean-at-all', default = True, dest = 'clean_everything', action = 'store_false', help = 'do not clean up the build')
        parser.add_argument('--run-all', default = False, dest = 'run_all', action = 'store_true', help = 'run everything (update, configure, make, install, tests)')
        parser.add_argument('--run-update', default = False, dest = 'run_update', action = 'store_true', help = 'fetch latest updates from git repository')
        parser.add_argument('--run-configure', default = False, dest = 'run_configure', action = 'store_true', help = 'run configure step')
        parser.add_argument('--run-make', default = False, dest = 'run_make', action = 'store_true', help = 'run make step')
        parser.add_argument('--run-install', default = False, dest = 'run_install', action = 'store_true', help = 'run install step')
        parser.add_argument('--run-tests', default = False, dest = 'run_tests', action = 'store_true', help = 'run tests step')
        parser.add_argument('--buildfarm', default = False, dest = 'buildfarm', action = 'store_true', help = 'run in buildfarm mode')
        parser.add_argument('--add-jobs-only', default = False, dest = 'add_jobs_only', action = 'store_true', help = 'only add new buildfarm jobs, do not execute them')
        parser.add_argument('--enable-orca', default = False, dest = 'enable_orca', action = 'store_true', help = 'build Orca as part of Greenplum Database')
        parser.add_argument('--extra-configure', default = '', dest = 'extra_configure', help = 'extra configure options')
        parser.add_argument('--extra-make', default = '', dest = 'extra_make', help = 'extra make options')
        parser.add_argument('--extra-install', default = '', dest = 'extra_install', help = 'extra make install options')
        parser.add_argument('--extra-tests', default = '', dest = 'extra_tests', help = 'extra make installcheck-good options')
        parser.add_argument('--patch', dest = 'patch', action = 'append', help = 'additional patch(es) to apply')
        parser.add_argument('--make-parallel', default = '', dest = 'make_parallel', help = 'number of parallel make jobs (default: 1)')
        parser.add_argument('--list-results', default = False, dest = 'list_results', action = 'store_true', help = 'list all locally stored results of previous runs')
        parser.add_argument('--show-result', default = '', dest = 'show_result', help = 'show results of a specific build (use "last" for latest build)')
        parser.add_argument('--list-jobs', default = False, dest = 'list_jobs', action = 'store_true', help = 'list all pending buildfarm jobs, then exit')
        parser.add_argument('--list-all-jobs', default = False, dest = 'list_all_jobs', action = 'store_true', help = 'list all pending and finished buildfarm jobs, then exit')
        parser.add_argument('--requeue-job', default = '', dest = 'requeue_job', help = 'requeue a buildfarm job')
        parser.add_argument('--no-send-results', default = True, dest = 'send_results', action = 'store_false', help = 'do not send test results to server')
        parser.add_argument('--build-branch', default = '', dest = 'build_branch', help = 'build this branch (or list of branches, separated by comma)')
        parser.add_argument('--build-revision', default = '', dest = 'build_revision', help = 'build this revision (defaults to HEAD)')
        parser.add_argument('--support-bin', default = '', dest = 'support_bin', help = "'buildclient_support.py' in the same directoy as the buildfarm client")
        parser.add_argument('--disable-support', default = False, dest = 'disable_support', action = 'store_true', help = 'do not create a support package (nothing will be uploaded)')
        parser.add_argument('--support-dir', default = '', dest = 'support_dir', help = 'optional directory for support files')
        parser.add_argument('--support-file', default = '', dest = 'support_file', help = 'optional filename for support file, must end in .zip or .tar')
        parser.add_argument('--support-archive-type', default = '', dest = 'support_archive_type', help = 'type of support archive: zip or tar')
        parser.add_argument('--lockfile', default = '', dest = 'lockfile', help = 'optional lockfile name (required for buildfarm mode)')
        parser.add_argument('--cleanup-builds', default = False, dest = 'cleanup_builds', action = 'store_true', help = 'cleanup all previous build and install directories')
        parser.add_argument('--cleanup-patches', default = False, dest = 'cleanup_patches', action = 'store_true', help = 'cleanup all previous patches in cache directory')
        parser.add_argument('--cleanup-support-files', default = False, dest = 'cleanup_support_files', action = 'store_true', help = 'cleanup all previous support files in build directory')
        parser.add_argument('--test-locales', default = '', dest = 'test_locales', help = 'comma-separated list of locales to test (PostgreSQL only)')
        parser.add_argument('--test-extra-targets', default = '', dest = 'test_extra_targets', help = 'space separated extra test targets (additional to "make check" in PostgreSQL or "make installcheck-good" in Greenplum"')
        parser.add_argument('-v', '--verbose', default = False, dest = 'verbose', action = 'store_true', help = 'be more verbose')
        parser.add_argument('-q', '--quiet', default = False, dest = 'quiet', action = 'store_true', help = 'run quietly')


        # parse parameters
        args = parser.parse_args()

        if (args.help is True):
            self.print_help()
            sys.exit(0)

        if (args.verbose is True and args.quiet is True):
            self.print_help()
            print("")
            print("Error: --verbose and --quiet can't be set at the same time")
            sys.exit(1)

        if (args.verbose is True):
            logging.getLogger().setLevel(logging.DEBUG)

        if (args.quiet is True):
            logging.getLogger().setLevel(logging.ERROR)

        self.__cmdline_read = 1
        self.arguments = args

        return



    # load_config()
    #
    # load configuration file (YAML)
    #
    # parameter:
    #  - self
    # return:
    #  none
    def load_config(self):
        if not (self.arguments.config):
            self.__configfile_read = 1
            self.configfile = False
            return

        logging.debug("config file: " + self.arguments.config)

        if (self.arguments.config and os.path.isfile(self.arguments.config) is False):
            self.print_help()
            print("")
            print("Error: --config is not a file")
            sys.exit(1)

        try:
            with open(self.arguments.config, 'r') as ymlcfg:
                config_file = yaml.safe_load(ymlcfg)
        except:
            print("")
            print("Error loading config file")
            sys.exit(1)

        #print(config_file['git']['executable'])
        self.configfile = config_file


        # prepopulate values, avoid nasty 'KeyError" later on
        self.pre_set_configfile_value('git', 'executable', None)
        self.pre_set_configfile_value('git', 'depth', None)

        self.pre_set_configfile_value('buildfarm', 'animal', None)
        self.pre_set_configfile_value('buildfarm', 'secret', None)
        self.pre_set_configfile_value('buildfarm', 'url', None)
        self.pre_set_configfile_value('buildfarm', 'send-results', None)
        self.pre_set_configfile_value('buildfarm', 'enabled', None)
        self.pre_set_configfile_value('buildfarm', 'add-jobs-only', None)

        self.pre_set_configfile_value('repository', 'url', None)

        # top-dir can only be present in the config file
        # pathnames on the commandline need to be fully specified
        self.pre_set_configfile_value('build', 'dirs', 'top-dir')
        self.pre_set_configfile_value('build', 'dirs', 'cache-dir')
        self.pre_set_configfile_value('build', 'dirs', 'build-dir')
        self.pre_set_configfile_value('build', 'dirs', 'install-dir')

        self.pre_set_configfile_value('build', 'patch', None)

        self.pre_set_configfile_value('build', 'options', 'no-clean-on-failure')
        self.pre_set_configfile_value('build', 'options', 'no-clean-at-all')
        self.pre_set_configfile_value('build', 'options', 'enable-orca')
        self.pre_set_configfile_value('build', 'options', 'extra-configure')
        self.pre_set_configfile_value('build', 'options', 'extra-make')
        self.pre_set_configfile_value('build', 'options', 'extra-install')
        self.pre_set_configfile_value('build', 'options', 'extra-tests')
        self.pre_set_configfile_value('build', 'options', 'ccache-bin')
        self.pre_set_configfile_value('build', 'options', 'make-parallel')
        self.pre_set_configfile_value('build', 'work', 'branch')
        self.pre_set_configfile_value('build', 'work', 'revision')

        self.pre_set_configfile_value('build', 'cleanup', 'cleanup-builds')
        self.pre_set_configfile_value('build', 'cleanup', 'cleanup-patches')
        self.pre_set_configfile_value('build', 'cleanup', 'cleanup-support-files')

        self.pre_set_configfile_value('support', 'executable', None)
        self.pre_set_configfile_value('support', 'disable-support', None)
        self.pre_set_configfile_value('support', 'support-dir', None)
        self.pre_set_configfile_value('support', 'support-file', None)
        self.pre_set_configfile_value('support', 'archive-type', None)

        self.pre_set_configfile_value('locking', 'lockfile', None)

        self.pre_set_configfile_value('test', 'locales', None)
        self.pre_set_configfile_value('test', 'extra-targets', None)


        self.__configfile_read = 1
        return



    # pre_set_configfile_value()
    #
    # make sure that the specified configfile parameter is initialized
    #
    # parameter:
    #  - name of first level
    #  - name of second level (or None)
    #  - name of third level (or None)
    def pre_set_configfile_value(self, pos1, pos2, pos3):
        if (pos1 is None):
            print("Error setting configfile value")
            sys.exit(1)
        if (pos3 is not None and pos2 is None):
            print("Error setting configfile value")
            sys.exit(1)

        if (pos2 is None):
            # just pos1 is specified, this makes pos1 an actual key
            # not a container for more config elements
            if not (pos1 in self.configfile):
                self.configfile[pos1] = ''
            if (self.configfile[pos1] is None):
                self.configfile[pos1] = ''
            return

        if (pos3 is None):
            # pos1 is a dictionary
            if not (pos1 in self.configfile):
                self.configfile[pos1] = {}
            if not (pos2 in self.configfile[pos1]):
                self.configfile[pos1][pos2] = ''
            if (self.configfile[pos1][pos2] is None):
                self.configfile[pos1][pos2] = ''
            return

        # pos1 and pos2 are dictionaries
        if not (pos1 in self.configfile):
            self.configfile[pos1] = {}
        if not (pos2 in self.configfile[pos1]):
            self.configfile[pos1][pos2] = {}
        if not (pos3 in self.configfile[pos1][pos2]):
            self.configfile[pos1][pos2][pos3] = ''
        if (self.configfile[pos1][pos2][pos3] is None):
            self.configfile[pos1][pos2][pos3] = ''

        return



    # replace_home_env()
    #
    # replace placeholder for home directory with actual directory name
    #
    # parameter:
    #  - self
    #  - directory name
    # return:
    #  - directory name
    def replace_home_env(self, dir):
        #dir = string.replace(dir, '$HOME', os.environ.get('HOME'))
        dir = dir.replace('$HOME', os.environ.get('HOME'))
        dir = dir.replace('$TOPDIR', self.configfile['build']['dirs']['top-dir'])
        dir = dir.replace('$HOME', os.environ.get('HOME'))
        return dir



    # build_and_verify_config()
    #
    # verify configuration,
    # create config from commandline and config file
    #
    # parameter:
    #  - self
    # return:
    #  none
    def build_and_verify_config(self):

        ret = {}

        if (self.arguments.verbose is True and self.arguments.quiet is True):
            self.print_help()
            print("")
            print("Error: --verbose and --quiet can't be set at the same time")
            sys.exit(1)

        if (self.arguments.verbose is True):
            logging.getLogger().setLevel(logging.DEBUG)
            ret['verbose'] = True
            ret['quiet'] = False

        if (self.arguments.quiet is True):
            logging.getLogger().setLevel(logging.ERROR)
            ret['verbose'] = False
            ret['quiet'] = True


        if (self.arguments.list_jobs is True):
            if (len(self.arguments.show_result) > 0 or
                self.arguments.list_results is True or
                self.arguments.list_all_jobs is True or
                len(self.arguments.requeue_job) > 0 or
                self.arguments.run_all is True or
                self.arguments.run_update is True or
                self.arguments.run_configure is True or
                self.arguments.run_make is True or
                self.arguments.run_install is True or
                self.arguments.run_tests is True):
                self.print_help()
                print("")
                print("Error: --list-jobs can't be combined with another run option")
                sys.exit(1)

        if (self.arguments.list_all_jobs is True):
            if (len(self.arguments.show_result) > 0 or
                self.arguments.list_results is True or
                self.arguments.list_jobs is True or
                len(self.arguments.requeue_job) > 0 or
                self.arguments.run_all is True or
                self.arguments.run_update is True or
                self.arguments.run_configure is True or
                self.arguments.run_make is True or
                self.arguments.run_install is True or
                self.arguments.run_tests is True):
                self.print_help()
                print("")
                print("Error: --list-all-jobs can't be combined with another run option")
                sys.exit(1)

        if (len(self.arguments.requeue_job) > 0):
            if (len(self.arguments.show_result) > 0 or
                self.arguments.list_results is True or
                self.arguments.list_jobs is True or
                self.arguments.list_all_jobs is True or
                self.arguments.run_all is True or
                self.arguments.run_update is True or
                self.arguments.run_configure is True or
                self.arguments.run_make is True or
                self.arguments.run_install is True or
                self.arguments.run_tests is True):
                self.print_help()
                print("")
                print("Error: --requeue-job can't be combined with another run option")
                sys.exit(1)

        if (self.arguments.list_results is True):
            if (len(self.arguments.show_result) > 0 or
                self.arguments.list_jobs is True or
                self.arguments.list_all_jobs is True or
                len(self.arguments.requeue_job) > 0 or
                self.arguments.run_all is True or
                self.arguments.run_update is True or
                self.arguments.run_configure is True or
                self.arguments.run_make is True or
                self.arguments.run_install is True or
                self.arguments.run_tests is True):
                self.print_help()
                print("")
                print("Error: --list-results can't be combined with another run option")
                sys.exit(1)

        if (len(self.arguments.show_result) > 0):
            if (self.arguments.list_results is True or
                self.arguments.list_jobs is True or
                self.arguments.list_all_jobs is True or
                len(self.arguments.requeue_job) > 0 or
                self.arguments.run_all is True or
                self.arguments.run_update is True or
                self.arguments.run_configure is True or
                self.arguments.run_make is True or
                self.arguments.run_install is True or
                self.arguments.run_tests is True):
                self.print_help()
                print("")
                print("Error: --show-result can't be combined with another run option")
                sys.exit(1)

        if (self.arguments.run_all is True):
            if (len(self.arguments.show_result) > 0 or
                self.arguments.list_results is True or
                self.arguments.list_jobs is True or
                self.arguments.list_all_jobs is True or
                len(self.arguments.requeue_job) > 0 or
                self.arguments.run_update is True or
                self.arguments.run_configure is True or
                self.arguments.run_make is True or
                self.arguments.run_install is True or
                self.arguments.run_tests is True):
                self.print_help()
                print("")
                print("Error: --run-all can't be combined with another run option")
                sys.exit(1)

        if (self.arguments.run_all is True):
            ret['show-result'] = ''
            ret['list-results'] = False
            ret['list-jobs'] = False
            ret['list-all-jobs'] = False
            ret['requeue-job'] = ''
            ret['run-update'] = True
            ret['run-configure'] = True
            ret['run-make'] = True
            ret['run-install'] = True
            ret['run-tests'] = True
        else:
            ret['show-result'] = self.arguments.show_result if (len(self.arguments.show_result) > 0) else ''
            ret['list-results'] = True if (self.arguments.list_results is True) else False
            ret['list-jobs'] = True if (self.arguments.list_jobs is True) else False
            ret['list-all-jobs'] = True if (self.arguments.list_all_jobs is True) else False
            ret['requeue-job'] = self.arguments.requeue_job if (len(self.arguments.requeue_job) > 0) else ''
            ret['run-update'] = True if (self.arguments.run_update is True) else False
            ret['run-configure'] = True if (self.arguments.run_configure is True) else False
            ret['run-make'] = True if (self.arguments.run_make is True) else False
            ret['run-install'] = True if (self.arguments.run_install is True) else False
            ret['run-tests'] = True if (self.arguments.run_tests is True) else False

        # do not require --run-update
        #if (ret['run-configure'] is True and ret['run-update'] is False):
        #    self.print_help()
        #    print("")
        #    print("Error: --run-configure requires --run-update")
        #    sys.exit(1)

        if (ret['run-make'] is True and ret['run-configure'] is False):
            self.print_help()
            print("")
            print("Error: --run-make requires --run-configure")
            sys.exit(1)

        if (ret['run-install'] is True and ret['run-make'] is False):
            self.print_help()
            print("")
            print("Error: --run-install requires --run-make")
            sys.exit(1)

        if (ret['run-tests'] is True and ret['run-install'] is False):
            self.print_help()
            print("")
            print("Error: --run-tests requires --run-install")
            sys.exit(1)


        if (self.arguments.cache_dir and os.path.isdir(self.arguments.cache_dir) is False):
            self.print_help()
            print("")
            print("Error: --cache-dir is not a directory")
            print("Argument: " + self.arguments.cache_dir)
            sys.exit(1)
        if (self.configfile is not False):
            if (len(self.configfile['build']['dirs']['cache-dir']) > 0 and os.path.isdir(self.replace_home_env(self.configfile['build']['dirs']['cache-dir'])) is False):
                self.print_help()
                print("")
                print("Error: cache-dir is not a directory")
                print("Argument: " + self.configfile['build']['dirs']['cache-dir'])
                sys.exit(1)
        if (self.arguments.cache_dir):
            ret['cache-dir'] = self.arguments.cache_dir
        elif (self.configfile is not False and self.configfile['build']['dirs']['cache-dir']):
            ret['cache-dir'] = self.replace_home_env(self.configfile['build']['dirs']['cache-dir'])
        else:
            self.print_help()
            print("")
            print("Error: cache-dir is not defined")
            sys.exit(1)
        if (ret['cache-dir'].find("'") != -1 or ret['cache-dir'].find('"') != -1):
            self.print_help()
            print("")
            print("Error: Invalid cache-dir name")
            print("Argument: " + ret['cache-dir'])
            sys.exit(1)


        if (self.arguments.build_dir and os.path.isdir(self.arguments.build_dir) is False):
            self.print_help()
            print("")
            print("Error: --build-dir is not a directory")
            print("Argument: " + self.arguments.build_dir)
            sys.exit(1)
        if (self.configfile is not False):
            if (len(self.configfile['build']['dirs']['build-dir']) > 0 and os.path.isdir(self.replace_home_env(self.configfile['build']['dirs']['build-dir'])) is False):
                self.print_help()
                print("")
                print("Error: build-dir is not a directory")
                print("Argument: " + self.configfile['build']['dirs']['build-dir'])
                sys.exit(1)
        if (self.arguments.build_dir):
            ret['build-dir'] = self.arguments.build_dir
        elif (self.configfile is not False and self.configfile['build']['dirs']['build-dir']):
            ret['build-dir'] = self.replace_home_env(self.configfile['build']['dirs']['build-dir'])
        else:
            self.print_help()
            print("")
            print("Error: build-dir is not defined")
            sys.exit(1)
        if (ret['build-dir'].find("'") != -1 or ret['build-dir'].find('"') != -1):
            self.print_help()
            print("")
            print("Error: Invalid build-dir name")
            print("Argument: " + ret['build-dir'])
            sys.exit(1)


        if (self.arguments.install_dir and os.path.isdir(self.arguments.install_dir) is False):
            self.print_help()
            print("")
            print("Error: --install-dir is not a directory")
            print("Argument: " + self.arguments.install_dir)
            sys.exit(1)
        if (self.configfile is not False):
            if (len(self.configfile['build']['dirs']['install-dir']) > 0 and os.path.isdir(self.replace_home_env(self.configfile['build']['dirs']['install-dir'])) is False):
                self.print_help()
                print("")
                print("Error: install-dir is not a directory")
                print("Argument: " + self.configfile['build']['dirs']['install-dir'])
                sys.exit(1)
        if (self.arguments.install_dir):
            ret['install-dir'] = self.arguments.install_dir
        elif (self.configfile is not False and self.configfile['build']['dirs']['install-dir']):
            ret['install-dir'] = self.replace_home_env(self.configfile['build']['dirs']['install-dir'])
        else:
            self.print_help()
            print("")
            print("Error: install-dir is not defined")
            sys.exit(1)
        if (ret['install-dir'].find("'") != -1 or ret['install-dir'].find('"') != -1):
            self.print_help()
            print("")
            print("Error: Invalid install-dir name")
            print("Argument: " + ret['install-dir'])
            sys.exit(1)


        stat_cache = os.stat(ret['cache-dir'])
        stat_build = os.stat(ret['build-dir'])
        if (stat_cache.st_dev != stat_build.st_dev):
            self.print_help()
            print("")
            print("Error: cache-dir and build-dir must be on the same filesystem")
            sys.exit(1)


        if (self.arguments.git_bin == ''):
            if (self.configfile is not False and len(self.configfile['git']['executable']) > 0):
                # use the executable from the configuration file
                if (self.binary_is_executable(self.configfile['git']['executable']) is False):
                    self.print_help()
                    print("")
                    print("Error: --git-bin is not an executable")
                    print("Argument: " + self.configfile['git']['executable'])
                    sys.exit(1)
                ret['git-bin'] = self.configfile['git']['executable']
            else:
                # find git binary in $PATH
                tmp_bin = self.find_in_path('git')
                if (tmp_bin is False):
                    self.print_help()
                    print("")
                    print("Error: no 'git' executable found")
                    sys.exit(1)
                ret['git-bin'] = tmp_bin
        else:
            if (self.binary_is_executable(self.arguments.git_bin) is False):
                self.print_help()
                print("")
                print("Error: --git-bin is not an executable")
                print("Argument: " + self.arguments.git_bin)
                sys.exit(1)
            ret['git-bin'] = self.arguments.git_bin

        # check 'git' version number
        null_file = open(os.devnull, 'w')
        v = subprocess.check_output([ret['git-bin'], '--version'], stderr=null_file)
        null_file.close()
        # make sure the extract ends in a number, this will cut of things like "rc..."
        v_r = re.match(b'git version ([\d\.]+\d)', v)
        if (v_r):
            logging.debug("'" + str(ret['git-bin']) + "' version: " + v_r.group(1).decode())
            self.arguments.git_version = v_r.group(1).decode()
        else:
            self.print_help()
            print("")
            print("Error: cannot identify 'git' version")
            sys.exit(1)
        # 'git' version must be 2.x.x, or greater
        v_v = self.arguments.git_version.split('.')
        try:
            v_v2 = int(v_v[0])
        except ValueError:
            self.print_help()
            print("")
            print("Error: cannot identify 'git' version")
            sys.exit(1)
        if (v_v2 < 2):
            self.print_help()
            print("")
            print("Error: minimum required 'git' version is 2")
            print("Found: " + self.arguments.git_version)
            sys.exit(1)
        # all git versions below 2.7.1 are vulnerable
        if (LooseVersion(self.arguments.git_version) <= LooseVersion('2.7.1')):
                logging.warning("git version (" + self.arguments.git_version + ") is vulnerable!")


        if (self.arguments.git_depth == ''):
            # read value from configfile
            if (self.configfile is not False and len(str(self.configfile['git']['depth'])) > 0):
                ret['git-depth'] = self.configfile['git']['depth']
            else:
                # default value (everything)
                ret['git-depth'] = 0
        else:
            # use input from commandline
            ret['git-depth'] = self.arguments.git_depth
        try:
            t = int(ret['git-depth'])
        except ValueError:
            self.print_help()
            print("")
            print("Error: git-depth is not an integer")
            sys.exit(1)
        if (t < 0):
            self.print_help()
            print("")
            print("Error: git-depth must be a positive integer")
            sys.exit(1)
        ret['git-depth'] = t


        if (self.arguments.send_results is False):
            # --no-send-results specified on commandline, honor the flag
            ret['send-results'] = False
        elif (self.arguments.send_results is True):
            # see if the configuration overrides this flag
            # FIXME: deal with non-integer values
            if (self.configfile is not False and self.configfile['buildfarm']['send-results'] == 1):
                ret['send-results'] = True
            else:
                ret['send-results'] = False


        if (self.arguments.animal):
            ret['buildfarm-animal'] = self.arguments.animal
        elif (self.configfile is not False and len(self.configfile['buildfarm']['animal']) > 0):
            ret['buildfarm-animal'] = self.configfile['buildfarm']['animal']
        else:
            if (ret['send-results'] == True):
                self.print_help()
                print("")
                print("Error: No buildfarm animal name specified")
                sys.exit(1)


        if (self.arguments.secret):
            ret['buildfarm-secret'] = self.arguments.secret
        elif (self.configfile is not False and len(self.configfile['buildfarm']['secret']) > 0):
            ret['buildfarm-secret'] = self.configfile['buildfarm']['secret']
        else:
            if (ret['send-results'] == True):
                self.print_help()
                print("")
                print("Error: No buildfarm animal secret specified")
                sys.exit(1)


        if (self.arguments.target):
            ret['buildfarm-url'] = self.arguments.target
        elif (self.configfile is not False and len(self.configfile['buildfarm']['url']) > 0):
            ret['buildfarm-url'] = self.configfile['buildfarm']['url']
        else:
            if (ret['send-results'] == True):
                self.print_help()
                print("")
                print("Error: No buildfarm url specified")
                sys.exit(1)


        if (self.arguments.buildfarm is True):
            # --buildfarm specified on commandline, honor the flag
            ret['buildfarm'] = True
        elif (self.arguments.buildfarm is False):
            # see if the configuration overrides this flag
            # FIXME: deal with non-integer values
            if (self.configfile is not False and self.configfile['buildfarm']['enabled'] == 1):
                ret['buildfarm'] = True
            else:
                ret['buildfarm'] = False


        if (self.arguments.add_jobs_only is True):
            # --add-jobs-only specified on commandline, honor the flag
            ret['add-jobs-only'] = True
        elif (self.arguments.add_jobs_only is False):
            # see if the configuration overrides this flag
            # FIXME: deal with non-integer values
            if (self.configfile is not False and self.configfile['buildfarm']['add-jobs-only'] == 1):
                ret['add-jobs-only'] = True
            else:
                ret['add-jobs-only'] = False


        if (ret['buildfarm'] is True):
            # certain options are not valid in buildfarm mode
            if (len(ret['show-result']) > 0):
                self.print_help()
                print("")
                print("Error: --show-result cannot be combined with --buildfarm")
                sys.exit(1)
            if (ret['list-results'] is True):
                self.print_help()
                print("")
                print("Error: --list-results cannot be combined with --buildfarm")
                sys.exit(1)
            if (ret['list-jobs'] is True):
                self.print_help()
                print("")
                print("Error: --list-jobs cannot be combined with --buildfarm")
                sys.exit(1)
            if (ret['list-all-jobs'] is True):
                self.print_help()
                print("")
                print("Error: --list-all-jobs cannot be combined with --buildfarm")
                sys.exit(1)
            if (len(ret['requeue-job']) > 0):
                self.print_help()
                print("")
                print("Error: --requeue-job cannot be combined with --buildfarm")
                sys.exit(1)
            if (ret['run-update'] is False):
                self.print_help()
                print("")
                print("Error: --run-update must be set when combined with --buildfarm")
                sys.exit(1)
            if (ret['run-configure'] is False):
                self.print_help()
                print("")
                print("Error: --run-configure must be set when combined with --buildfarm")
                sys.exit(1)
            if (ret['run-make'] is False):
                self.print_help()
                print("")
                print("Error: --run-make must be set when combined with --buildfarm")
                sys.exit(1)
            if (ret['run-install'] is False):
                self.print_help()
                print("")
                print("Error: --run-install must be set when combined with --buildfarm")
                sys.exit(1)
            if (ret['run-tests'] is False):
                self.print_help()
                print("")
                print("Error: --run-tests must be set when combined with --buildfarm")
                sys.exit(1)

        if (ret['add-jobs-only'] is True and ret['buildfarm'] is False):
            self.print_help()
            print("")
            print("Error: --add-jobs-only requires --buildfarm")
            sys.exit(1)

        if (ret['buildfarm'] is True):
            # need a 'tar' binary
            # the original buildfarm, by default, uses the one provided by the system
            # find tar binary in $PATH
            tmp_bin = self.find_in_path('tar')
            if (tmp_bin is False):
                self.print_help()
                print("")
                print("Error: no 'tar' executable found")
                sys.exit(1)
            ret['tar-bin'] = tmp_bin


        # do not really check if a valid repository is specified, let git deal with it
        if (self.arguments.source):
            ret['repository-url'] = self.arguments.source
        elif (self.configfile is not False and len(self.configfile['repository']['url'])) > 0:
            ret['repository-url'] = self.configfile['repository']['url']
        else:
            #self.print_help()
            #print("")
            #print("Error: No repository url specified")
            #sys.exit(1)
            # do not check for a repository here
            # there are certain actions which do not require a repository
            ret['repository-url'] = ""


        if (self.arguments.clean_on_failure is False):
            # --no-clean-on-failure specified on commandline, honor the flag
            ret['clean-on-failure'] = False
        elif (self.arguments.clean_on_failure is True):
            # see if the configuration overrides this flag
            if (self.configfile is not False and self.configfile['build']['options']['no-clean-on-failure'] == 1):
                ret['clean-on-failure'] = True
            else:
                ret['clean-on-failure'] = False


        if (self.arguments.clean_everything is False):
            # --no-clean-at-all specified on commandline, honor the flag
            ret['clean-everything'] = False
        elif (self.arguments.clean_everything is True):
            # see if the configuration overrides this flag
            if (self.configfile is not False and self.configfile['build']['options']['no-clean-at-all'] == 1):
                ret['clean-everything'] = True
            else:
                ret['clean-everything'] = False


        if (self.arguments.build_branch == ''):
            if (self.configfile is not False and len(self.configfile['build']['work']['branch']) > 0):
                ret['build-branch'] = self.configfile['build']['work']['branch']
            else:
                # set to reasonable default value
                ret['build-branch'] = 'master'
        else:
            ret['build-branch'] = self.arguments.build_branch
        if (ret['build-branch'].find(',') != -1):
            # more than one branch specified
            ret['build-branch'] = ret['build-branch'].split(',')
        else:
            # only one branch
            ret['build-branch'] = [ ret['build-branch'] ]
        for branch in ret['build-branch']:
            if (branch.find('/') != -1):
                self.print_help()
                print("")
                print("Error: Invalid branch name (only local branches allowed)")
                print("Argument: " + branch)
                sys.exit(1)
            if (branch.find("'") != -1 or branch.find('"') != -1):
                self.print_help()
                print("")
                print("Error: Invalid branch name")
                print("Argument: " + branch)
                sys.exit(1)


        if (self.arguments.build_revision == ''):
            if (self.configfile is not False and len(self.configfile['build']['work']['revision']) > 0):
                ret['build-revision'] = self.configfile['build']['work']['revision']
            else:
                # set to reasonable default value
                ret['build-revision'] = 'HEAD'
        else:
            ret['build-revision'] = self.arguments.build_revision
        if (len(ret['build-branch']) > 1 and len(ret['build-revision']) > 0 and ret['build-revision'] != 'HEAD'):
            self.print_help()
            print("")
            print("Error: Multiple branches specified, not possible to specify a revision")
            sys.exit(1)
        if not (re.match("^[a-zA-Z0-9]+$", ret['build-revision'])):
            self.print_help()
            print("")
            print("Error: Invalid revision name")
            print("Argument: " + ret['build-revision'])
            sys.exit(1)


        if (self.arguments.extra_configure == ''):
            if (self.configfile is not False and len(self.configfile['build']['options']['extra-configure']) > 0):
                ret['extra-configure'] = self.configfile['build']['options']['extra-configure']
            else:
                ret['extra-configure'] = ''
        else:
            ret['extra-configure'] = self.arguments.extra_configure


        if (self.arguments.extra_make == ''):
            if (self.configfile is not False and len(self.configfile['build']['options']['extra-make']) > 0):
                ret['extra-make'] = self.configfile['build']['options']['extra-make']
            else:
                ret['extra-make'] = ''
        else:
            ret['extra-make'] = self.arguments.extra_make


        if (self.arguments.extra_install == ''):
            if (self.configfile is not False and len(self.configfile['build']['options']['extra-install']) > 0):
                ret['extra-install'] = self.configfile['build']['options']['extra-install']
            else:
                ret['extra-install'] = ''
        else:
            ret['extra-install'] = self.arguments.extra_install


        if (self.arguments.extra_tests == ''):
            if (self.configfile is not False and len(self.configfile['build']['options']['extra-tests']) > 0):
                ret['extra-tests'] = self.configfile['build']['options']['extra-tests']
            else:
                ret['extra-tests'] = ''
        else:
            ret['extra-tests'] = self.arguments.extra_tests


        if (self.arguments.ccache_bin == ''):
            if (self.configfile is not False and len(self.configfile['build']['options']['ccache-bin']) > 0):
                ret['ccache-bin'] = self.configfile['build']['options']['ccache-bin']
            else:
                ret['ccache-bin'] = ''
        else:
            ret['ccache-bin'] = self.arguments.ccache_bin

        if (len(ret['ccache-bin']) > 0):
            if (self.binary_is_executable(ret['ccache-bin']) is False):
                if (ret['ccache-bin'].find(os.sep) == -1):
                    # no directory separator, just the binary name - try to find it in $PATH
                    ccache_bin = self.find_in_path(ret['ccache-bin'])
                    if (ccache_bin is False):
                        self.print_help()
                        print("")
                        print("Error: no --ccache-bin executable found")
                        print("Argument: " + ret['ccache-bin'])
                        sys.exit(1)
                    ret['ccache-bin'] = ccache_bin
                else:
                    # directory separator found, but binary does not exist
                    self.print_help()
                    print("")
                    print("Error: --ccache-bin is not an executable")
                    print("Argument: " + ret['ccache-bin'])
                    sys.exit(1)
            if (os.environ.get('CC') is not None):
                if (os.environ.get('CC').find("ccache") != -1):
                    self.print_help()
                    print("")
                    print("Error: --ccache-bin specified, but already set in environment")
                    print("Argument: " + ret['ccache-bin'])
                    print("$CC: " + os.environ.get('CC'))
                    sys.exit(1)
            if (os.environ.get('CXX') is not None):
                if (os.environ.get('CXX').find("ccache") != -1):
                    self.print_help()
                    print("")
                    print("Error: --ccache-bin specified, but already set in environment")
                    print("Argument: " + ret['ccache-bin'])
                    print("$CXX: " + os.environ.get('CXX'))
                    sys.exit(1)


        if (self.arguments.make_parallel == ''):
            # read value from configfile
            if (self.configfile is not False and len(str(self.configfile['build']['options']['make-parallel'])) > 0):
                ret['make-parallel'] = self.configfile['build']['options']['make-parallel']
            else:
                # default value (just one job)
                ret['make-parallel'] = 1
        else:
            # use input from commandline
            ret['make-parallel'] = self.arguments.make_parallel
        try:
            t = int(ret['make-parallel'])
        except ValueError:
            self.print_help()
            print("")
            print("Error: make-parallel is not an integer")
            sys.exit(1)
        if (t < 0):
            self.print_help()
            print("")
            print("Error: make-parallel must be a positive integer")
            sys.exit(1)
        ret['make-parallel'] = t


        if (self.arguments.enable_orca is True):
            # --enable-orca specified on commandline, honor the flag
            ret['enable-orca'] = True
        elif (self.arguments.enable_orca is False):
            # see if the configuration overrides this flag
            if (self.configfile is not False and self.configfile['build']['options']['enable-orca'] == 1):
                ret['enable-orca'] = True
            else:
                ret['enable-orca'] = False
        if (ret['enable-orca'] is True):
            print("")
            print("Error: --enable-orca is not yet supported")
            sys.exit(1)


        if (self.arguments.disable_support is True):
            # --disable-support specified on commandline, honor the flag
            ret['disable-support'] = True
        elif (self.arguments.disable_support is False):
            # see if the configuration overrides this flag
            if (self.configfile is not False and self.configfile['support']['disable-support'] == 1):
                ret['disable-support'] = True
            else:
                ret['disable-support'] = False


        if (ret['disable-support'] is False):
            ret['support-bin'] = ''
            if (self.arguments.support_bin == ''):
                if (self.configfile is not False and len(self.configfile['support']['executable']) > 0):
                    # use the executable from the configuration file
                    if not (os.access(self.configfile['support']['executable'], os.X_OK)):
                        self.print_help()
                        print("")
                        print("Error: --support-bin is not an executable")
                        print("Argument: " + self.configfile['support']['executable'])
                        sys.exit(1)
                    ret['git-bin'] = self.configfile['git']['executable']
                else:
                    # find binary in same directory as this program
                    ret['support-bin'] = ''
                    current_path = os.path.dirname(os.path.abspath(__file__))
                    current_bin = os.path.join(current_path, 'buildclient_support.py')
                    if (os.access(current_bin, os.X_OK)):
                        ret['support-bin'] = current_bin
                        logging.debug("found buildclient support tool: " + current_bin)
            else:
                if not (os.access(self.arguments.support_bin, os.X_OK)):
                    self.print_help()
                    print("")
                    print("Error: --support-bin is not an executable")
                    print("Argument: " + self.arguments.support_bin)
                    sys.exit(1)
                ret['support-bin'] = self.arguments.support_bin
        else:
            ret['support-bin'] = ''


        if (self.arguments.support_archive_type == ''):
            if (self.configfile is not False and len(self.configfile['support']['archive-type']) > 0):
                ret['support-archive-type'] = self.configfile['support']['archive-type']
            else:
                # defaults to zip
                ret['support-archive-type'] = 'zip'
        else:
            ret['support-archive-type'] = self.arguments.support_archive_type
        if (ret['support-archive-type'] != 'zip' and ret['support-archive-type'] != 'tar'):
            self.print_help()
            print("")
            print("Error: --support-archive-type must be 'zip' or 'tar'")
            print("Argument: " + ret['support-archive-type'])
            sys.exit(1)


        if (self.arguments.support_dir == ''):
            if (self.configfile is not False and len(self.configfile['support']['support-dir']) > 0):
                ret['support-dir'] = self.configfile['support']['support-dir']
            else:
                ret['support-dir'] = ''
        else:
            ret['support-dir'] = self.arguments.support_dir
        if (len(ret['support-dir']) > 0):
            # verify that the directory exists
            if (os.path.isdir(ret['support-dir']) is False):
                self.print_help()
                print("")
                print("Error: --support-dir is not a directory")
                print("Argument: " + ret['support-dir'])
                sys.exit(1)


        if (self.arguments.support_file == ''):
            if (self.configfile is not False and len(self.configfile['support']['support-file']) > 0):
                ret['support-file'] = self.configfile['support']['support-file']
            else:
                ret['support-file'] = ''
        else:
            ret['support-file'] = self.arguments.support_file
        if (len(ret['support-file']) > 0):
            # verify that the file ends in ".zip" or ".tar"
            if (ret['support-file'][-4:] != '.zip' and ret['support-file'][-4:] != '.tar'):
                self.print_help()
                print("")
                print("Error: --support-file must end in '.zip' or '.tar'")
                print("Argument: " + ret['support-file'])
                sys.exit(1)
            # do not check if the file exists - not our responsibility
            # verify that the file ending matches the requested type
            if (ret['support-file'][-4:] == '.zip' and ret['support-archive-type'] != 'zip'):
                self.print_help()
                print("")
                print("Error: --support-file must end in '.zip' if --support-archive-type is 'zip'")
                print("Argument: " + ret['support-file'])
                sys.exit(1)
            if (ret['support-file'][-4:] == '.tar' and ret['support-archive-type'] != 'tar'):
                self.print_help()
                print("")
                print("Error: --support-file must end in '.tar' if --support-archive-type is 'tar'")
                print("Argument: " + ret['support-file'])
                sys.exit(1)


        if (len(ret['support-dir']) > 0 and len(ret['support-file']) > 0):
            self.print_help()
            print("")
            print("Error: --support-dir and --support-file specified, only one option possible")
            sys.exit(1)


        if (isinstance(self.arguments.patch, list)):
            # at least one patch specified
            ret['patch'] = list(self.arguments.patch)
        else:
            # no patch specified on command line, check configuration file
            if (self.configfile is not False and len(self.configfile['build']['patch']) > 0):
                ret['patch'] = list(self.configfile['build']['patch'])
            else:
                # no entries
                ret['patch'] = []
        if (ret['buildfarm'] is True and len(ret['patch']) > 0):
            self.print_help()
            print("")
            print("Error: patches cannot be specified in --buildfarm mode")
            sys.exit(1)


        if (self.arguments.cleanup_builds is True):
            # --cleanup-builds specified on commandline, honor the flag
            ret['cleanup-builds'] = True
        elif (self.arguments.cleanup_builds is False):
            # see if the configuration overrides this flag
            # FIXME: deal with non-integer values
            if (self.configfile is not False and self.configfile['build']['cleanup']['cleanup-builds'] == 1):
                ret['cleanup-builds'] = True
            else:
                ret['cleanup-builds'] = False

        if (self.arguments.cleanup_patches is True):
            # --cleanup-patches specified on commandline, honor the flag
            ret['cleanup-patches'] = True
        elif (self.arguments.cleanup_patches is False):
            # see if the configuration overrides this flag
            # FIXME: deal with non-integer values
            if (self.configfile is not False and self.configfile['build']['cleanup']['cleanup-patches'] == 1):
                ret['cleanup-patches'] = True
            else:
                ret['cleanup-patches'] = False

        if (self.arguments.cleanup_support_files is True):
            # --cleanup-support-files specified on commandline, honor the flag
            ret['cleanup-support-files'] = True
        elif (self.arguments.cleanup_support_files is False):
            # see if the configuration overrides this flag
            # FIXME: deal with non-integer values
            if (self.configfile is not False and self.configfile['build']['cleanup']['cleanup-support-files'] == 1):
                ret['cleanup-support-files'] = True
            else:
                ret['cleanup-support-files'] = False

        if (ret['buildfarm'] is True):
            if (ret['cleanup-builds'] is True):
                self.print_help()
                print("")
                print("Error: --buildfarm mode and --cleanup-builds can't be combined")
                sys.exit(1)
            if (ret['cleanup-patches'] is True):
                self.print_help()
                print("")
                print("Error: --buildfarm mode and --cleanup-patches can't be combined")
                sys.exit(1)
            if (ret['cleanup-support-files'] is True):
                self.print_help()
                print("")
                print("Error: --buildfarm mode and --cleanup-support-files can't be combined")
                sys.exit(1)


        if (self.arguments.test_locales == ''):
            if (self.configfile is not False and len(self.configfile['test']['locales']) > 0):
                ret['test-locales'] = self.configfile['test']['locales']
            else:
                ret['test-locales'] = ''
        else:
            ret['test-locales'] = self.arguments.test_locales
        if (ret['test-locales'].find(" ") != -1):
            # check that no spaces are in the string
            self.print_help()
            print("")
            print("Error: locales in --test-locales must be separated by comma")
            print("Argument: " + ret['test-locales'])
            sys.exit(1)


        if (self.arguments.test_extra_targets == ''):
            if (self.configfile is not False and len(self.configfile['test']['extra-targets']) > 0):
                ret['test-extra-targets'] = self.configfile['test']['extra-targets']
            else:
                ret['test-extra-targets'] = ''
        else:
            ret['test-extra-targets'] = self.arguments.test_extra_targets
        if (ret['test-extra-targets'].find(",") != -1):
            # check that no commas are in the string
            self.print_help()
            print("")
            print("Error: test targets in --test-extra-targets must be separated by spaces")
            print("Argument: " + ret['test-extra-targets'])
            sys.exit(1)


        if (self.arguments.lockfile == ''):
            if (self.configfile is not False and len(self.replace_home_env(self.configfile['locking']['lockfile'])) > 0):
                ret['lockfile'] = self.replace_home_env(self.configfile['locking']['lockfile'])
            else:
                ret['lockfile'] = ''
        else:
            ret['lockfile'] = self.arguments.lockfile
        if (ret['buildfarm'] is True):
            # buildfarm requires a lockfile
            if (len(ret['lockfile']) == 0):
                self.print_help()
                print("")
                print("Error: a lockfile is required for --buildfarm mode")
                sys.exit(1)

        if (len(ret['lockfile']) > 0):
            lock = LockFile(ret['lockfile'])
            logging.debug("trying to acquire lock on " + ret['lockfile'])
            if not lock.i_am_locking():
                try:
                    lock.acquire(timeout = 1)
                    logging.debug("acquired lock on " + ret['lockfile'])
                except LockTimeout:
                    logging.error("can't acquire lock on " + ret['lockfile'])
                    # just bail out here, something else is locking the lockfile
                    sys.exit(1)
            self.lockfile_handle = lock
            self.lockfile_name = ret['lockfile']



        self.__fully_initiated = 1
        self.config = ret

        return ret



    # get()
    #
    # get a specific config setting
    #
    # parameter:
    #  - self
    #  - config setting name
    # return:
    #  - config value
    # note:
    #  - will abort if the configuration is not yet initialized
    #  - will abort if the config setting is not initialized
    def get(self, name):
        if (self.__fully_initiated != 1):
            print("")
            print("Error: config is not initialized!")
            sys.exit(1)
        if (name in self.config):
            return self.config[name]
        else:
            print("")
            print("Error: requested config value does not exist!")
            print("Value: " + name)
            sys.exit(1)



    # getall()
    #
    # return a list of all config keys
    #
    # parameter:
    #  - self
    # return:
    #  - list with all config keys, sorted
    def getall(self):
        if (self.__fully_initiated != 1):
            print("")
            print("Error: config is not initialized!")
            sys.exit(1)

        return sorted(list(self.config.keys()))



    # isset()
    #
    # verifies if a specific config setting is initialized
    #
    # parameter:
    #  - self
    #  - config setting name
    # return:
    #  - True/False
    # note:
    #  - will abort if the configuration is not yet initialized
    def isset(self, name):
        if (self.__fully_initiated != 1):
            print("")
            print("Error: config is not initialized!")
            sys.exit(1)
        if (name in self.config):
            return True
        else:
            return False



    # set()
    #
    # set a specific config setting to a new value
    #
    # parameter:
    #  - self
    #  - config setting name
    #  - new value
    # return:
    #  none
    # note:
    #  - will abort if the configuration is not yet initialized
    def set(self, name, value):
        if (self.__fully_initiated != 1):
            print("")
            print("Error: config is not initialized!")
            sys.exit(1)
        self.config[name] = value



    # create_hashname()
    #
    # creates a hashname based on the input name
    #
    # parameter:
    #  - self
    #  - input name
    # return:
    #  - hash string
    def create_hashname(self, name):
        result = hashlib.md5(name.encode('utf-8')).hexdigest()
        logging.debug("hashname: " + name + " -> " + result)

        return result



    # from: http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    # human_size()
    #
    # format number into human readable output
    #
    # parameters:
    #  - self
    #  - number
    # return:
    #  - string with formatted number
    def human_size(self, size_bytes):
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



    # binary_is_executable()
    #
    # verify if a specified binary is executable
    #
    # parameter:
    #  - self
    #  - binary name
    # return:
    #  - True/False
    # note:
    #  - does not work on Windows
    def binary_is_executable(self, bin):
        if (os.access(bin, os.X_OK)):
            return True

        return False



    # find_in_path()
    #
    # find a specific binary in $PATH
    #
    # parameter:
    #  - self
    #  - binary name
    # return:
    #  - binary with path, or False
    # note:
    #  - does not work on Windows
    def find_in_path(self, bin):
        # Python 3.3 and newer have shutil.which()
        # Note: this does not work on Windows
        for p in os.environ["PATH"].split(os.pathsep):
            e = os.path.join(p, bin)
            if (self.binary_is_executable(e) is True):
                # found a binary
                return e

        return False



    # cleanup_old_dirs_and_files()
    #
    # cleanup old directories, patches and build support files
    #
    # parameter:
    #  - self
    # return:
    #  none
    def cleanup_old_dirs_and_files(self):
        # note: not the best place for this function, but usually the Config module
        # is initialized way before the other modules
        if (self.get('cleanup-builds') is True):
            # cleanup all directories in the 'build' and 'install' directory, which match a certain pattern
            found = []
            for entry in os.listdir(self.get('build-dir')):
                if (os.path.isdir(os.path.join(self.get('build-dir'), entry))):
                    found.append(os.path.join(self.get('build-dir'), entry))
            for entry in os.listdir(self.get('install-dir')):
                if (os.path.isdir(os.path.join(self.get('install-dir'), entry))):
                    found.append(os.path.join(self.get('install-dir'), entry))

            for entry in found:
                entry_match = re.search(r'[\/\\]\d\d\d\d\-\d\d\-\d\d_\d\d\d\d\d\d_', entry)
                if (entry_match):
                    logging.info("remove directory: " + str(entry))
                    shutil.rmtree(entry, ignore_errors=True)
                    if (os.path.isfile(entry + '.diff')):
                        logging.info("remove patch: " + str(entry) + '.diff')
                        os.remove(entry + '.diff')

        if (self.get('cleanup-patches') is True):
            # cleanup all files in the 'cache' directory, which match a certain pattern
            found = []
            for entry in os.listdir(self.get('cache-dir')):
                if (os.path.isfile(os.path.join(self.get('cache-dir'), entry))):
                    found.append(os.path.join(self.get('cache-dir'), entry))

            for entry in found:
                entry_match = re.search(r'[\/\\][a-f0-9]+\.diff$', entry)
                if (entry_match):
                    logging.info("remove patch: " + str(entry))
                    os.remove(entry)
                entry_match = re.search(r'[\/\\][a-f0-9]+\.diff.unpacked$', entry)
                if (entry_match):
                    logging.info("remove patch: " + str(entry))
                    os.remove(entry)

        if (self.get('cleanup-support-files') is True):
            # cleanup all files in the 'build' directory, which match a certain pattern
            found = []
            for entry in os.listdir(self.get('build-dir')):
                if (os.path.isfile(os.path.join(self.get('build-dir'), entry))):
                    found.append(os.path.join(self.get('build-dir'), entry))

            for entry in found:
                stats = os.stat(entry)
                # if someone zips a build directory, it should be bigger than ~10MB
                if (stats.st_size > 100000 and stats.st_size < 10000000):
                    entry_match = re.search(r'[\/\\].+\.zip$', entry)
                    if (entry_match):
                        logging.info("remove support file: " + str(entry))
                        os.remove(entry)




    # logfile_name()
    #
    # generate a filename for a logfile
    #
    # parameter:
    #  - self
    #  - type of logfile (git, configure, make, install, tests)
    #  - second logfile number, optional, will be formatted to 2 digits
    #  - second logfile type, optional
    #  - second file type, optional (cmdline, exit_code, stdout_stderr, logfile)
    #  - full path, optional (directory must be specified, .txt will be added)
    # return:
    #  logfile name
    def logfile_name(self, log_type, second_number = None, second_type = None, file_type = None, full_path = False):
        filename = "log_"

        if (log_type == "git"):
            filename += "01_git"
        elif (log_type == "configure"):
            filename += "02_configure"
        elif (log_type == "make"):
            filename += "03_make"
        elif (log_type == "install"):
            filename += "04_make_install"
        elif (log_type == "tests"):
            filename += "05_tests"
        else:
            logging.error("unknown log_type: " + str(log_type))
            sys.exit(1)

        if (second_number is not None):
            filename += '_{0:02d}'.format(int(second_number))

        if (second_type is not None):
            filename += "_" + str(second_type)

        if (file_type is not None):
            if (file_type == "cmdline" or file_type == "exit_code" or
                file_type == "stdout_stderr" or file_type == "logfile"):
                filename += "_" + file_type
            else:
                logging.error("unknown file_type: " + str(file_type))
                sys.exit(1)

        if (full_path is not False):
            if not (os.path.exists(full_path)):
                logging.error("directory path does not exist: " + str(full_path))
                sys.exit(1)
            filename = os.path.join(full_path, filename + ".txt")

        return filename


