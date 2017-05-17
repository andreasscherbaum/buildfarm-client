import re
import os
import stat
import sys
import shutil
import subprocess
import argparse
import yaml
import logging
import time
import atexit
from subprocess import Popen, PIPE
import shlex
import datetime
import glob
import sys
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf8')




class RegressionTestErrorPG(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


# this class must be initialized per repository/branch/revision

class Build:

    def __init__(self, config, repository, build_dir):
        self.config = config
        self.repository = repository
        self.build_dir = build_dir
        self.install_dir = False
        # holds scripts to execute on cleanup
        self.cleanup_exec = []
        # holds files and directories to remove in case of error
        self.cleanup_error = []
        # holds files and directories to remove when instance is destroyed
        self.cleanup_clean = []
        # holds all the support archives
        self.support_archives = []
        # logfile directory, valid during Greenplum tests
        self.regression_logfile_directory = False

        # directory which holds the buildfarm logfiles
        self.buildfarm_logs = os.path.join(build_dir, '.buildfarm-logs')
        # create directory for buildfarm logfiles
        os.mkdir(self.buildfarm_logs, 0o0700)

        atexit.register(self.exit_handler)



    def exit_handler(self):
        for script in self.cleanup_exec:
            logging.debug("execute cleanup script: " + script)
            run = self.run_shell(script)
            # throw away the result
        for entry in self.cleanup_error:
            if (os.path.isdir(entry)):
                logging.debug("remove directory after error: " + entry)
                shutil.rmtree(entry, ignore_errors=True)
            if (os.path.isfile(entry)):
                logging.debug("remove file after error: " + entry)
                try:
                    os.remove(entry)
                except OSError as e:
                    logging.error("failed to remove file: " + entry)
                    logging.error("error: " + e.strerror)
        for entry in self.cleanup_clean:
            if (os.path.isdir(entry)):
                logging.debug("remove clean directory: " + entry)
                shutil.rmtree(entry, ignore_errors=True)
            if (os.path.isfile(entry)):
                logging.debug("remove clean file: " + entry)
                try:
                    os.remove(entry)
                except OSError as e:
                    logging.error("failed to remove file: " + entry)
                    logging.error("error: " + e.strerror)



    # add_support_archive()
    #
    # store a support archive path
    #
    # parameter:
    #  - self
    #  - path to archive
    # return:
    #  none
    def add_support_archive(self, script):
        self.support_archives.append(script)



    # list_all_support_archives()
    #
    # list all stored support archives
    #
    # parameter:
    #  - self
    # return:
    #  - list of created support archives
    def list_all_support_archives(self):
        return self.support_archives



    # add_script_to_delete_exec()
    #
    # execute a script before the repository is deleted
    #
    # parameter:
    #  - self
    #  - path to script
    # return:
    #  none
    def add_script_to_delete_exec(self, script):
        self.cleanup_exec.append(script)



    # add_entry_to_delete_error()
    #
    # remember file or directory to be deleted in case of error
    #
    # parameter:
    #  - self
    #  - path name
    # return:
    #  none
    def add_entry_to_delete_error(self, entry):
        if (self.config.get('clean-everything') is False):
            logging.debug("not cleaning up: " + entry)
        else:
            if (self.config.get('clean-on-failure') == True):
                self.cleanup_error.append(entry)



    # add_entry_to_delete_clean()
    #
    # remember file or directory to be deleted when instance is destroyed
    #
    # parameter:
    #  - self
    #  - path name
    # return:
    #  none
    def add_entry_to_delete_clean(self, entry):
        if (self.config.get('clean-everything') is False):
            logging.debug("not cleaning up: " + entry)
        else:
            self.cleanup_clean.append(entry)



    # portcheck()
    #
    # check socketfiles for TCP ports
    #
    # parameter:
    #  - self
    #  - repository type
    #  - log data object
    # return:
    #  - True/False
    def portcheck(self, repository_type, log_data):
        if (repository_type == 'PostgreSQL'):
            log_data['result_portcheck'] = 0
            # PostgreSQL usually uses '57832', or $PGPORT
            ports = ['57832']
            if (os.environ.get('PGPORT') is not None and len(os.environ.get('PGPORT')) > 0):
                ports.append(os.environ.get('PGPORT'))

            sockets_exist = []
            for port in ports:
                if (os.path.exists('/tmp/.s.PGSQL.' + port)):
                    sockets_exist.append('/tmp/.s.PGSQL.' + port)

            if (len(sockets_exist) > 0):
                # at least one port is blocked
                log_data['errorstr'] = 'Socket file(s) exists: ' + ", ".join(sockets_exist)
                logging.error(log_data['errorstr'])
                log_data['result_portcheck'] = 1
                return False
            else:
                log_data['result_portcheck'] = 0
                return True

        elif (repository_type == 'Greenplum'):
            # ports are hardcoded for now, although the Greenplum suite allows it to change the ports
            ports = ['15432']
            for i in range(25432, 25432 + 20):
                ports.append(str(i))
            if (os.environ.get('PGPORT') is not None and len(os.environ.get('PGPORT')) > 0):
                ports.append(os.environ.get('PGPORT'))

            sockets_exist = []
            for port in ports:
                if (os.path.exists('/tmp/.s.PGSQL.' + port)):
                    sockets_exist.append('/tmp/.s.PGSQL.' + port)

            if (len(sockets_exist) > 0):
                # at least one port is blocked
                log_data['errorstr'] = 'Socket file(s) exists: ' + ", ".join(sockets_exist)
                logging.error(log_data['errorstr'])
                log_data['result_portcheck'] = 1
                return False
            else:
                log_data['result_portcheck'] = 0
                return True

        else:
            logging.error("Unsupported repository type: " + repository_type)
            sys.exit(1)



    # run_configure()
    #
    # run "./configure" command in build directory
    #
    # parameter:
    #  - self
    #  - optional extra options for "configure"
    #  - name of the build directory (without path)
    #  - pointer to log data
    # return:
    #  - True/False (False if error)
    def run_configure(self, extra_options, build_dir_name, log_data):
        self.extra_configure_options = extra_options
        install_dir = self.config.get('install-dir')

        # write 'githead.log'
        f = open(os.path.join(self.buildfarm_logs, 'githead.log'), 'w')
        f.write(log_data['revision'])
        f.close()

        full_install_dir = os.path.join(install_dir, build_dir_name)
        self.install_dir = full_install_dir
        logging.info("install dir: " + full_install_dir)

        repository_type = self.repository.identify_repository_type(self.build_dir)

        execute = "./configure --prefix='" + full_install_dir + "'"
        # FIXME: Orca
        if (len(extra_options) > 0):
            execute += ' ' + extra_options

        if (repository_type == 'PostgreSQL'):
            execute += ' --with-pgport=5678'
        # FIXME: remove existing --with-pgport from configure line

        run = self.run_shell(execute)
        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("configure"))
        log_data['run_configure'] = True
        log_data['extra_configure'] = extra_options
        log_data['result_configure'] = run[0]
        log_data['time_configure'] = run[2]

        # before handling an error during configure, create 'configure.log' and 'config.log' in the log directory
        # keep metadata (like mtime) intact, the PostgreSQL buildfarm depends on it
        self.copy_logfile(self.config.logfile_name("configure", file_type = 'stdout_stderr', full_path = self.build_dir), os.path.join(self.buildfarm_logs, 'configure.log'))
        self.copy_logfile(os.path.join(self.build_dir, 'config.log'), os.path.join(self.buildfarm_logs, 'config.log'))

        if (run[0] > 0):
            self.print_run_error(run, execute)
            return False


        # read version information from src/include/pg_config.h
        f = open(os.path.join(self.build_dir, 'src', 'include', 'pg_config.h'), 'rU')
        for line in iter(f):
            line = line.rstrip('\n')

            v = re.match('^#define PG_MAJORVERSION "(.+?)"', line)
            if (v):
                log_data['pg_majorversion'] = v.group(1)
                #print("pg_majorversion: " + v.group(1))
                continue

            v = re.match('^#define PG_VERSION "(.+?)"', line)
            if (v):
                log_data['pg_version'] = v.group(1)
                #print("pg_version: " + v.group(1))
                continue

            v = re.match('^#define PG_VERSION_NUM (\d+)', line)
            if (v):
                log_data['pg_version_num'] = v.group(1)
                #print("pg_version_num: " + v.group(1))
                continue

            v = re.match('^#define PG_VERSION_STR "(.+?)"', line)
            if (v):
                log_data['pg_version_str'] = v.group(1)
                #print("pg_version_str: " + v.group(1))
                continue

            v = re.match('^#define GP_MAJORVERSION "(.+?)"', line)
            if (v):
                log_data['gp_majorversion'] = v.group(1)
                #print("gp_majorversion: " + v.group(1))
                continue

            v = re.match('^#define GP_VERSION "(.+?)"', line)
            if (v):
                log_data['gp_version'] = v.group(1)
                #print("gp_version: " + v.group(1))
                continue

            v = re.match('^#define GP_VERSION_NUM (\d+)', line)
            if (v):
                log_data['gp_version_num'] = v.group(1)
                #print("gp_version_num: " + v.group(1))
                continue

        f.close()

        return True



    # run_make()
    #
    # run "make" in build directory
    #
    # parameter:
    #  - self
    #  - optional extra options for "make"
    #  - pointer to log data
    # return:
    #  - True/False (False if error)
    def run_make(self, extra_options, log_data):
        self.extra_make_options = extra_options
        # FIXME: ccache
        #ccache_bin = self.config.get('ccache-bin')
        make_parallel = self.config.get('make-parallel')

        execute = "make"
        if (make_parallel > 1):
            execute += ' -j ' + str(make_parallel)
        if (len(extra_options) > 0):
            execute += ' ' + extra_options
        run = self.run_shell(execute)
        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("make"))
        log_data['run_make'] = True
        log_data['extra_make'] = extra_options
        log_data['result_make'] = run[0]
        log_data['time_make'] = run[2]

        # before handling an error during configure, create 'make.log' in the log directory
        # keep metadata (like mtime) intact, the PostgreSQL buildfarm depends on it
        self.copy_logfile(self.config.logfile_name("make", file_type = 'stdout_stderr', full_path = self.build_dir), os.path.join(self.buildfarm_logs, 'make.log'))

        if (run[0] > 0):
            self.print_run_error(run, execute)
            return False

        return True



    # run_make_install()
    #
    # run "make install" in build directory
    #
    # parameter:
    #  - self
    #  - optional extra options for "make install"
    #  - pointer to log data
    #  - extra options for make
    # return:
    #  - False (if error)
    #  - path to install dir
    def run_make_install(self, extra_options, log_data, make_extra_options):
        self.extra_install_options = extra_options

        execute = "make install"
        if (len(extra_options) > 0):
            execute += ' ' + extra_options
        run = self.run_shell(execute)
        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("install"))
        log_data['run_install'] = True
        log_data['extra_install'] = extra_options
        log_data['result_install'] = run[0]
        log_data['time_install'] = run[2]
        if (run[0] > 0):
            self.print_run_error(run, execute)
            return False


        repository_type = self.repository.identify_repository_type(self.build_dir)

        if (repository_type == 'PostgreSQL'):
            make_parallel = self.config.get('make-parallel')

            make_execute = "make"
            make_execute_parallel = "make"
            if (make_parallel > 1):
                make_execute_parallel += ' -j ' + str(make_parallel)
            if (len(make_extra_options) > 0):
                make_execute += ' ' + make_extra_options
                make_execute_parallel += ' ' + make_extra_options


            # create script to run 'make check'
            filename = os.path.join(self.build_dir, 'buildclient_run_regression_tests.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write('set -e' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(make_execute + " check" + os.linesep)
            # FIXME: run additional targets
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            datadirs = os.path.join(self.install_dir, "tmp_demo_db")

            # initialize and start the database
            filename = os.path.join(self.install_dir, 'buildclient_initdb.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write('set -e' + os.linesep)
            f.write("" + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            f.write("mkdir -p '" + datadirs + "'" + os.linesep)
            f.write("./bin/initdb -D '" + datadirs + "'" + os.linesep)
            f.write("echo 'port = 15432' >> '" + os.path.join(datadirs, 'postgresql.conf') + "'" + os.linesep)
            f.write("./bin/pg_ctl -D '" + datadirs + "' -l '" + os.path.join(datadirs, 'logfile') + "' start" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will start psql + arguments
            filename = os.path.join(self.install_dir, 'buildclient_psql.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write('set -e' + os.linesep)
            f.write("" + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            f.write('./bin/psql -p 15432 "$@"' + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will start arbitrary tools
            filename = os.path.join(self.install_dir, 'buildclient_debug.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write('set -e' + os.linesep)
            f.write("" + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            f.write("set -x" + os.linesep);
            f.write("" + os.linesep);
            f.write("# build dir: " + self.build_dir + os.linesep);
            f.write("# install dir: " + self.install_dir + os.linesep);
            f.write("" + os.linesep);
            f.write('# add your script here' + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will generate a support package
            if (self.config.get("support-bin")):
                filename = os.path.join(self.install_dir, 'buildclient_support.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("" + os.linesep);
                f.write(self.config.get("support-bin") + " --archive-type " + self.config.get('support-archive-type') + "" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will start the database
            filename = os.path.join(self.install_dir, 'buildclient_start_db.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write('set -e' + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            f.write("./bin/pg_ctl -D '" + datadirs + "' -l '" + os.path.join(datadirs, 'logfile') + "' start" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will stop the database
            filename = os.path.join(self.install_dir, 'buildclient_stop_db.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write('set -e' + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            f.write("./bin/pg_ctl -D '" + datadirs + "' -m fast stop" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)
            # stop the cluster when the module is destroyed
            self.add_script_to_delete_exec(filename)




            if (log_data['is_buildfarm'] is True):
                # create script to run the buildfarm regression tests (make check)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_regression_tests.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                # FIXME: add locales, add user
                # FIXME: start server separately
                #f.write("make check" + os.linesep)
                f.write("cd " + os.path.join('src', 'test', 'regress') + os.linesep)
                f.write(make_execute + " NO_LOCALE=1 check" + os.linesep)
                # FIXME: run additional targets: run_extra_targets
                # FIXME: test_locales
                # FIXME: stop server
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (make contrib)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_make_contrib.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd contrib" + os.linesep)
                if (int(log_data['pg_version_num']) >= 90100):
                    f.write(make_execute_parallel + "" + os.linesep)
                else:
                    f.write(make_execute + "" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (make testmodules)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_make_testmodules.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'test', 'modules') + os.linesep)
                f.write(make_execute_parallel + "" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (make install in contrib)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_make_contrib-install.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd contrib" + os.linesep)
                f.write(make_execute + " install" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (make install in modules)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_make_testmodules-install.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'test', 'modules') + os.linesep)
                f.write(make_execute + " install" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                if (int(log_data['pg_version_num']) >= 90200):
                    # create script to run the buildfarm regression tests (test upgrade)
                    filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_make_pg_upgrade.sh')
                    f = open(filename, 'w')
                    f.write('#!/bin/sh' + os.linesep + os.linesep)
                    f.write('set -e' + os.linesep)
                    f.write("cd '" + self.build_dir + "'" + os.linesep)
                    f.write("export PGHOST=/tmp" + os.linesep)
                    if (int(log_data['pg_version_num']) >= 90500):
                        f.write("cd " + os.path.join('src', 'bin', 'pg_upgrade') + os.linesep)
                    else:
                        f.write("cd " + os.path.join('contrib', 'pg_upgrade') + os.linesep)
                    f.write(make_execute + " check" + os.linesep)
                    f.close()
                    os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (test-decoding-check)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_make_test-decoding-check.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('contrib', 'test_decoding') + os.linesep)
                f.write(make_execute + " check" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (initdb with locale)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_initdb.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.install_dir + "'" + os.linesep)
                f.write("./bin/initdb -U ads --locale=$1 data-$1" + os.linesep)
                f.write("cat buildfarm_append_postgresql.conf >> data-$1/postgresql.conf" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)
                # create part of a config file which will be appended to the main config
                filename = os.path.join(self.install_dir, 'buildfarm_append_postgresql.conf')
                f = open(filename, 'w')
                f.write(os.linesep + os.linesep)
                f.write("# settings for buildfarm:" + os.linesep)
                f.write("log_line_prefix = '%m [%c:%l] '" + os.linesep)
                f.write("log_connections = 'true'" + os.linesep)
                f.write("log_disconnections = 'true'" + os.linesep)
                f.write("log_statement = 'all'" + os.linesep)
                f.write("fsync = off" + os.linesep)
                f.close()

                # create script to run the buildfarm regression tests (start database)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_startdb.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.install_dir + "'" + os.linesep)
                # the original buildfarm uses the same logfile, and deletes it every time
                # use a different logfile each time instead
                f.write("./bin/pg_ctl -D data-$1 -l logfile-$1-$2 -w start" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (stop database)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_stopdb.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.install_dir + "'" + os.linesep)
                f.write("export PGCTLTIMEOUT=120" + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write("./bin/pg_ctl -D data-$1 stop" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (shutdown database after failure)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_stopdbs_after_failure.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                #f.write('set -e' + os.linesep)
                f.write("cd '" + self.install_dir + "'" + os.linesep)
                f.write("export PGCTLTIMEOUT=120" + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write("mkdir data-failure" + os.linesep)
                f.write("for d in data*; do" + os.linesep)
                f.write("./bin/pg_ctl -m immediate -l logfile_stop_after_failure -D $d stop" + os.linesep)
                f.write("done" + os.linesep)
                f.write("exit 0" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (installcheck)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_installcheck.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'test', 'regress') + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write(make_execute + " installcheck" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (isolation-check)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_isolation-check.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'test', 'isolation') + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write(make_execute + " NO_LOCALE=1 installcheck" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (pl-installcheck)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_pl-installcheck.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'pl') + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write(make_execute + " installcheck" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (contrib-installcheck)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_contrib-installcheck.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('contrib') + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write(make_execute + " USE_MODULE_DB=1 installcheck" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (testmodules-installcheck)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_testmodules-installcheck.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'test', 'modules') + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write(make_execute + " USE_MODULE_DB=1 installcheck" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

                # create script to run the buildfarm regression tests (ecpg-check)
                filename = os.path.join(self.build_dir, 'buildclient_run_buildfarm_ecpg-check.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write('set -e' + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("cd " + os.path.join('src', 'interfaces', 'ecpg') + os.linesep)
                #f.write("export PGUSER=ads" + os.linesep)
                f.write(make_execute + " NO_LOCALE=1 check" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


        elif (repository_type == 'Greenplum'):

            # create script to start and stop the demo cluster
            # and to run the test suite

            datadirs = os.path.join(self.install_dir, "tmp_regression_tests")

            # make cluster script (starts the cluster)
            filename = os.path.join(self.install_dir, 'buildclient_make_cluster.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("# try passwordless ssh login to localhost" + os.linesep)
            f.write("ssh -oBatchMode=yes localhost 'exit 0'" + os.linesep)
            f.write("result=$?" + os.linesep)
            f.write('if [ "$result" -ne "0" ];' + os.linesep)
            f.write("then" + os.linesep)
            f.write("\techo 'ssh login without password is not working!'" + os.linesep)
            f.write("\techo 'please verify your ssh configuration.'" + os.linesep)
            f.write("\texit 1" + os.linesep)
            f.write("fi" + os.linesep)
            f.write("" + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, "greenplum_path.sh") + "'" + os.linesep)
            f.write("cd gpAux/gpdemo" + os.linesep)
            # debug:
            f.write("export DATADIRS='" + datadirs + "'" + os.linesep)
            # FIXME: make ports dynamic
            # FIXME: make directory dynamic
            f.write("export MASTER_PORT=15432" + os.linesep)
            f.write("export PORT_BASE=25432" + os.linesep)
            f.write("" + os.linesep)
            f.write("make cluster" + os.linesep)
            f.write("#. gpdemo-env.sh" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # extract MASTER_DATA_DIRECTORY
            #/home/ads/postgresql/buildfarm/build/2016-03-01_185803_master/gpAux/gpdemo/datadirs/qddir/demoDataDir-1


            # script which will start psql + arguments
            filename = os.path.join(self.install_dir, 'buildclient_psql.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write(". '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            #f.write("export MASTER_DATA_DIRECTORY='" . os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'datadirs', 'qddir', 'demoDataDir-1') + "'" + os.linesep)
            f.write('psql "$@"' + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will start arbitrary tools
            filename = os.path.join(self.install_dir, 'buildclient_debug.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write(". '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            #f.write("export MASTER_DATA_DIRECTORY='" . os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'datadirs', 'qddir', 'demoDataDir-1') + "'" + os.linesep)
            f.write("" + os.linesep);
            f.write("set -x" + os.linesep);
            f.write("" + os.linesep);
            f.write("# build dir: " + self.build_dir + os.linesep);
            f.write("# install dir: " + self.install_dir + os.linesep);
            f.write("" + os.linesep);
            f.write('# add your script here' + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will generate a support package
            if (self.config.get("support-bin")):
                filename = os.path.join(self.install_dir, 'buildclient_support.sh')
                f = open(filename, 'w')
                f.write('#!/bin/sh' + os.linesep + os.linesep)
                f.write("cd '" + self.build_dir + "'" + os.linesep)
                f.write("" + os.linesep);
                f.write(self.config.get("support-bin") + " --archive-type " + self.config.get('support-archive-type') + " --logfiles '" + os.path.join(datadirs, "gpAdminLogs") + "'" + os.linesep)
                f.close()
                os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will start the cluster
            filename = os.path.join(self.install_dir, 'buildclient_start_cluster.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write("if [ -f '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "' ];" + os.linesep)
            f.write("then" + os.linesep)
            f.write("   . '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            #f.write("export MASTER_DATA_DIRECTORY='" . os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'datadirs', 'qddir', 'demoDataDir-1') + "'" + os.linesep)
            f.write("   gpstart -a" + ' -l "$MASTER_DATA_DIRECTORY/../gpAdminLogs"' + os.linesep)
            #f.write("   gpstart -a" + os.linesep)
            f.write("fi" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will stop the cluster
            filename = os.path.join(self.install_dir, 'buildclient_stop_cluster.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write("if [ -f '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "' ];" + os.linesep)
            f.write("then" + os.linesep)
            f.write("   . '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            #f.write("export MASTER_DATA_DIRECTORY='" . os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'datadirs', 'qddir', 'demoDataDir-1') + "'" + os.linesep)
            f.write("   gpstop -a" + ' -l "$MASTER_DATA_DIRECTORY/../gpAdminLogs"' + os.linesep)
            #f.write("   gpstop -a" + os.linesep)
            f.write("fi" + os.linesep)
            f.write("" + os.linesep)
            f.write("# there is a problem hidden in the gpMgmt scripts, which leaves an empty" + os.linesep)
            f.write("# logfile around in ~/gpAdminLogs/, even if a log directory is specified" + os.linesep)
            f.write("# remove empty files in the default log directory" + os.linesep)
            f.write("find ~/gpAdminLogs/ -type f -empty -atime -1 -mtime -1 -exec rm {} \;" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)
            # stop the cluster when the module is destroyed
            self.add_script_to_delete_exec(filename)


            # combine everything into one script which runs the regression tests
            filename = os.path.join(self.build_dir, 'buildclient_run_regression_tests.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            #f.write('set -e' + os.linesep + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            # for debugging purpose:
            #f.write("exit 1" + os.linesep)
            f.write("./buildclient_make_cluster.sh" + os.linesep)
            f.write("" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write("if [ -f '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "' ];" + os.linesep)
            f.write("then" + os.linesep)
            f.write("   . '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            f.write("fi" + os.linesep)
            # for debugging purpose:
            #f.write("exit 1" + os.linesep)
            f.write("make installcheck-world" + os.linesep)
            f.write("result=$?" + os.linesep)
            f.write("" + os.linesep)
            f.write("cd '" + self.install_dir + "'" + os.linesep)
            f.write("./buildclient_stop_cluster.sh" + os.linesep)
            f.write("" + os.linesep)
            f.write("exit $result" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will run bugbuster tests
            filename = os.path.join(self.install_dir, 'buildclient_bugbuster.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write("if [ -f '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "' ];" + os.linesep)
            f.write("then" + os.linesep)
            f.write("   . '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            #f.write("export MASTER_DATA_DIRECTORY='" . os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'datadirs', 'qddir', 'demoDataDir-1') + "'" + os.linesep)
            f.write("   export PATH='" + os.path.join(self.install_dir, 'bin') + "':$PATH" + os.linesep)
            # change this when dynamic ports are used
            f.write("   export PGPORT=15432" + os.linesep)
            f.write("   cd '" + os.path.join(self.build_dir, 'src', 'test', 'regress') + "'" + os.linesep)
            f.write("   ./pg_regress --psqldir='" + os.path.join(self.install_dir, 'tmp_regression_tests', 'qddir', 'demoDataDir-1') + "' --schedule=./bugbuster/known_good_schedule --psqldir='" + os.path.join(self.install_dir, 'bin') + "' --inputdir=bugbuster" + os.linesep)
            f.write("fi" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)


            # script which will run one regression test
            filename = os.path.join(self.install_dir, 'buildclient_run_one_regression_test.sh')
            f = open(filename, 'w')
            f.write('#!/bin/sh' + os.linesep + os.linesep)
            f.write("cd '" + self.build_dir + "'" + os.linesep)
            f.write(". '" + os.path.join(self.install_dir, 'greenplum_path.sh') + "'" + os.linesep)
            f.write("if [ -f '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "' ];" + os.linesep)
            f.write("then" + os.linesep)
            f.write("   . '" + os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'gpdemo-env.sh') + "'" + os.linesep)
            #f.write("export MASTER_DATA_DIRECTORY='" . os.path.join(self.build_dir, 'gpAux', 'gpdemo', 'datadirs', 'qddir', 'demoDataDir-1') + "'" + os.linesep)
            f.write("   export PATH='" + os.path.join(self.install_dir, 'bin') + "':$PATH" + os.linesep)
            # change this when dynamic ports are used
            f.write("   export PGPORT=15432" + os.linesep)
            f.write("   cd '" + os.path.join(self.build_dir, 'src', 'test', 'regress') + "'" + os.linesep)
            f.write("   ./pg_regress --psqldir='" + os.path.join(self.install_dir, 'tmp_regression_tests', 'qddir', 'demoDataDir-1') + "' --psqldir='" + os.path.join(self.install_dir, 'bin') + "' --inputdir=expected " + '"$@"'+ os.linesep)
            f.write("fi" + os.linesep)
            f.close()
            os.chmod(filename, stat.S_IRWXU | stat.S_IRWXG)

        return self.install_dir



    # run_tests()
    #
    # run tests in build directory
    #
    # parameter:
    #  - self
    #  - optional extra options for tests
    #  - pointer to log data
    # return:
    #  - True/False (False if error)
    def run_tests(self, extra_options, log_data):
        self.extra_tests_options = extra_options

        # FIXME: extra_options
        # FIXME: run_extra_targets


        repository_type = self.repository.identify_repository_type(self.build_dir)

        if (repository_type == 'PostgreSQL'):
            # FIXME: buildfarm timings
            if (log_data['is_buildfarm'] is True):
                execute = "./buildclient_run_buildfarm_regression_tests.sh"
            else:
                execute = "./buildclient_run_regression_tests.sh"
            run = self.run_shell(execute)
            test_log_number = 0
            self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number))
            log_data['run_tests'] = True
            log_data['extra_tests'] = extra_options
            log_data['result_tests'] = run[0]
            log_data['time_tests'] = run[2]

            self.copy_logfile(self.config.logfile_name("tests", second_number = test_log_number, file_type = 'stdout_stderr', full_path = self.build_dir), os.path.join(self.buildfarm_logs, 'check.log'))

            # add more logfiles, 'check.log' is a mingle-mangle of logs
            files_log = glob.glob(os.path.join(self.build_dir, 'src', 'test', 'regress', 'log') + os.sep + '*.log')
            files_log.extend(glob.glob(os.path.join(self.build_dir, 'tmp_install', 'log') + os.sep + '*'))
            if (os.path.isfile(os.path.join(self.build_dir, 'src', 'test', 'regress', 'regression.diffs'))):
                files_log[:0] = [os.path.join(self.build_dir, 'src', 'test', 'regress', 'regression.diffs')]
            for file_log in files_log:
                self.attach_logfile_pg_buildfarm(file_log,
                                                 os.path.join(self.buildfarm_logs, 'check.log'),
                                                 "\n\n================== " + file_log[len(self.build_dir) + 1:] + " ===================\n")
                self.attach_logfile_buildfarm(file_log,
                                              "tests", test_log_number, None,
                                              file_log[len(self.build_dir) + 1:])

            # add stack traces of any "core*" file found in the tree
            stack_trace = self.stack_traces(self.build_dir)
            if (len(stack_trace) > 0):
                f = open(os.path.join(self.buildfarm_logs, 'check.log'), 'a')
                f.write(stack_trace)
                f.close()
                f = open(self.config.logfile_name("tests", file_type = 'logfile', full_path = self.build_dir, second_number = test_log_number), 'a')
                f.write(stack_trace)
                f.close()

            # set mtime and other metadata to original timestamp from the test
            self.copy_stats(self.config.logfile_name("tests", second_number = test_log_number, file_type = 'stdout_stderr', full_path = self.build_dir), os.path.join(self.buildfarm_logs, 'check.log'))

            # finally deal with any error
            if (run[0] > 0):
                self.print_run_error(run, execute)
                return False

            # run "Contrib"
            if (log_data['is_buildfarm'] is True):
                execute = "./buildclient_run_buildfarm_make_contrib.sh"
                run = self.run_shell(execute)
                test_log_number += 1
                test_log_name = "make_contrib"
                self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                  os.path.join(self.buildfarm_logs, 'make-contrib.log'))

                # finally deal with any error
                if (run[0] > 0):
                    self.print_run_error(run, execute)
                    return False

            # run "TestModules"
            if (log_data['is_buildfarm'] is True):
                execute = "./buildclient_run_buildfarm_make_testmodules.sh"
                run = self.run_shell(execute)
                test_log_number += 1
                test_log_name = "make_testmodules"
                self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                  os.path.join(self.buildfarm_logs, 'make-testmodules.log'))

                # finally deal with any error
                if (run[0] > 0):
                    self.print_run_error(run, execute)
                    return False

            # install happened earlier, just copy the logfile
            self.copy_logfile(self.config.logfile_name("install", file_type = 'stdout_stderr', full_path = self.build_dir), os.path.join(self.buildfarm_logs, 'make-install.log'))
            if (log_data['is_buildfarm'] is True):
                # fake the metadata
                self.copy_stats(os.path.join(self.buildfarm_logs, 'make-testmodules.log'), os.path.join(self.buildfarm_logs, 'make-install.log'))

            # run "ContribInstall"
            if (log_data['is_buildfarm'] is True):
                execute = "./buildclient_run_buildfarm_make_contrib-install.sh"
                run = self.run_shell(execute)
                test_log_number += 1
                test_log_name = "make_contrib-install"
                self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                  os.path.join(self.buildfarm_logs, 'install-contrib.log'))

                # finally deal with any error
                if (run[0] > 0):
                    self.print_run_error(run, execute)
                    return False

            # run "TestModulesInstall"
            if (log_data['is_buildfarm'] is True):
                execute = "./buildclient_run_buildfarm_make_testmodules-install.sh"
                run = self.run_shell(execute)
                test_log_number += 1
                test_log_name = "make_testmodules-install"
                self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                  os.path.join(self.buildfarm_logs, 'install-testmodules.log'))

                # finally deal with any error
                if (run[0] > 0):
                    self.print_run_error(run, execute)
                    return False

            # run "pg_upgradeCheck"
            if (log_data['is_buildfarm'] is True and int(log_data['pg_version_num']) >= 90200):
                execute = "./buildclient_run_buildfarm_make_pg_upgrade.sh"
                run = self.run_shell(execute)
                test_log_number += 1
                test_log_name = "make_pg_upgrade"
                self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                  os.path.join(self.buildfarm_logs, 'check-pg_upgrade.log'))

                # add logfiles from tests
                files_log = glob.glob(os.path.join(self.build_dir, 'contrib', 'pg_upgrade') + os.sep + '*.log')
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'contrib', 'pg_upgrade', 'log') + os.sep + '*'))
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'src', 'bin', 'pg_upgrade') + os.sep + '*.log'))
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'src', 'bin', 'pg_upgrade', 'log') + os.sep + '*'))
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'src', 'test', 'regress') + os.sep + '*.diffs'))
                for file_log in files_log:
                    self.attach_logfile_pg_buildfarm(file_log,
                                                     os.path.join(self.buildfarm_logs, 'check-pg_upgrade.log'),
                                                     "=========================== " + file_log[len(self.build_dir) + 1:] + " ================\n")
                    self.attach_logfile_buildfarm(file_log,
                                                  "tests", test_log_number, test_log_name,
                                                  file_log[len(self.build_dir) + 1:])

                # set mtime and other metadata to original timestamp from the test
                self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                os.path.join(self.buildfarm_logs, 'check-pg_upgrade.log'))

                # finally deal with any error
                if (run[0] > 0):
                    self.print_run_error(run, execute)
                    return False

            # run "test-decoding-check"
            if (log_data['is_buildfarm'] is True):
                execute = "./buildclient_run_buildfarm_make_test-decoding-check.sh"
                run = self.run_shell(execute)
                test_log_number += 1
                test_log_name = "make_test-decoding-check"
                self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                  os.path.join(self.buildfarm_logs, 'test-decoding-check.log'))

                # add logfiles from tests
                files_log = glob.glob(os.path.join(self.build_dir, 'contrib', 'test_decoding', 'regression_output', 'log') + os.sep + '*.log')
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'contrib', 'test_decoding', 'regression_output') + os.sep + '*.diffs'))
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'contrib', 'test_decoding', 'isolation_output', 'log') + os.sep + '*.log'))
                files_log.extend(glob.glob(os.path.join(self.build_dir, 'contrib', 'test_decoding', 'isolation_output') + os.sep + '*.diffs'))
                for file_log in files_log:
                    self.attach_logfile_pg_buildfarm(file_log,
                                                     os.path.join(self.buildfarm_logs, 'test-decoding-check.log'),
                                                     "=========================== " + file_log[len(self.build_dir) + 1:] + " ================\n")
                    self.attach_logfile_buildfarm(file_log,
                                                  "tests", test_log_number, test_log_name,
                                                  file_log[len(self.build_dir) + 1:])

                # set mtime and other metadata to original timestamp from the test
                self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                os.path.join(self.buildfarm_logs, 'test-decoding-check.log'))

                # finally deal with any error
                if (run[0] > 0):
                    self.print_run_error(run, execute)
                    return False

            if (log_data['is_buildfarm'] is True):
                started_times = 0
                test_locales = log_data['test_locales']
                if (len(test_locales) == 0):
                    test_locales = 'C'
                test_locales = test_locales.split(',')
                for test_locale in test_locales:
                    # test each locale separately
                    # but run all tests for one locale before starting the next one

                    try:
                        # run "Initdb-<locale>"
                        test_log_number += 1
                        test_log_name = "initdb"
                        result = self.regression_pg_initdb(extra_options, log_data, test_locale, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('initdb')


                        # run "StartDb-<locale>"
                        started_times += 1
                        test_log_number += 1
                        test_log_name = "startdb"
                        result = self.regression_pg_startdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('startdb')


                        # run "InstallCheck-<locale>"
                        execute = "./buildclient_run_buildfarm_installcheck.sh" + " " + str(test_locale) + " " + str(started_times)
                        run = self.run_shell(execute)
                        test_log_number += 1
                        test_log_name = "make_installcheck"
                        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                          os.path.join(self.buildfarm_logs, 'install-check-' + str(test_locale) + '.log'))

                        # add logfiles
                        self.attach_logfile_pg_buildfarm(os.path.join(self.build_dir, 'src', 'test', 'regress', 'regression.diffs'),
                                                         os.path.join(self.buildfarm_logs, 'install-check-' + str(test_locale) + '.log'),
                                                         "\n\n================== src/test/regress/regression.diffs ==================\n")
                        self.attach_logfile_buildfarm(os.path.join(self.build_dir, 'src', 'test', 'regress', 'regression.diffs'),
                                                      "tests", test_log_number, test_log_name,
                                                      "src/test/regress/regression.diffs")

                        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                         os.path.join(self.buildfarm_logs, 'install-check-' + str(test_locale) + '.log'),
                                                         "\n\n================== logfile ==================\n")
                        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                      "tests", test_log_number, test_log_name,
                                                      "db logfile")

                        # set mtime and other metadata to original timestamp from the test
                        self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                        os.path.join(self.buildfarm_logs, 'install-check-' + str(test_locale) + '.log'))

                        # finally deal with any error
                        if (run[0] > 0):
                            self.print_run_error(run, execute)
                            raise RegressionTestErrorPG('make_installcheck')


                        # run "StopDb-<locale>"
                        test_log_number += 1
                        test_log_name = "stopdb"
                        result = self.regression_pg_stopdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('stopdb')




                        # run "StartDb-<locale>"
                        started_times += 1
                        test_log_number += 1
                        test_log_name = "startdb"
                        result = self.regression_pg_startdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('startdb')


                        # run "IsolationCheck-<locale>"
                        execute = "./buildclient_run_buildfarm_isolation-check.sh" + " " + str(test_locale) + " " + str(started_times)
                        run = self.run_shell(execute)
                        test_log_number += 1
                        test_log_name = "make_isolation-check"
                        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                          os.path.join(self.buildfarm_logs, 'isolation-check-' + str(test_locale) + '.log'))

                        # add logfiles
                        self.attach_logfile_pg_buildfarm(os.path.join(self.build_dir, 'src', 'test', 'isolation', 'regression.diffs'),
                                                         os.path.join(self.buildfarm_logs, 'isolation-check-' + str(test_locale) + '.log'),
                                                         "\n\n================== src/test/regress/regression.diffs ===================\n")

                        files_log = glob.glob(os.path.join(self.build_dir, 'src', 'test', 'isolation', 'log') + os.sep + '*.log')
                        for file_log in files_log:
                            self.attach_logfile_pg_buildfarm(file_log,
                                                             os.path.join(self.buildfarm_logs, 'isolation-check-' + str(test_locale) + '.log'),
                                                             "\n\n================== " + file_log[len(self.build_dir) + 1:] + " ===================\n")
                            self.attach_logfile_buildfarm(file_log,
                                                          "tests", test_log_number, test_log_name,
                                                          file_log[len(self.build_dir) + 1:])

                        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                         os.path.join(self.buildfarm_logs, 'isolation-check-' + str(test_locale) + '.log'),
                                                         "\n\n================== logfile ===================\n")
                        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                      "tests", test_log_number, test_log_name,
                                                      "db logfile")

                        # set mtime and other metadata to original timestamp from the test
                        self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                        os.path.join(self.buildfarm_logs, 'isolation-check-' + str(test_locale) + '.log'))

                        # finally deal with any error
                        if (run[0] > 0):
                            self.print_run_error(run, execute)
                            raise RegressionTestErrorPG('make_isolation-check')


                        # run "StopDb-<locale>"
                        test_log_number += 1
                        test_log_name = "stopdb"
                        result = self.regression_pg_stopdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('stopdb')




                        # run "StartDb-<locale>"
                        started_times += 1
                        test_log_number += 1
                        test_log_name = "startdb"
                        result = self.regression_pg_startdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('startdb')


                        # run "PLCheck-<locale>"
                        execute = "./buildclient_run_buildfarm_pl-installcheck.sh" + " " + str(test_locale) + " " + str(started_times)
                        run = self.run_shell(execute)
                        test_log_number += 1
                        test_log_name = "pl-installcheck"
                        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                          os.path.join(self.buildfarm_logs, 'pl-install-check-' + str(test_locale) + '.log'))

                        # add logfiles
                        files_log = glob.glob(os.path.join(self.build_dir, 'src', 'pl') + os.sep + '*' + os.sep + 'regression.diffs')
                        files_log.extend(glob.glob(os.path.join(self.build_dir, 'src', 'pl') + os.sep + '*' + os.sep + '*' + os.sep + 'regression.diffs'))
                        for file_log in files_log:
                            self.attach_logfile_pg_buildfarm(file_log,
                                                             os.path.join(self.buildfarm_logs, 'pl-install-check-' + str(test_locale) + '.log'),
                                                             "\n\n================= " + file_log[len(self.build_dir) + 1:] + " ===================\n")
                            self.attach_logfile_buildfarm(file_log,
                                                          "tests", test_log_number, test_log_name,
                                                          file_log[len(self.build_dir) + 1:])

                        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                         os.path.join(self.buildfarm_logs, 'pl-install-check-' + str(test_locale) + '.log'),
                                                         "\n\n================= logfile ===================\n")
                        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                      "tests", test_log_number, test_log_name,
                                                      "db logfile")

                        # set mtime and other metadata to original timestamp from the test
                        self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                        os.path.join(self.buildfarm_logs, 'pl-install-check-' + str(test_locale) + '.log'))

                        # finally deal with any error
                        if (run[0] > 0):
                            self.print_run_error(run, execute)
                            raise RegressionTestErrorPG('pl-installcheck')


                        # run "StopDb-<locale>"
                        test_log_number += 1
                        test_log_name = "stopdb"
                        result = self.regression_pg_stopdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('stopdb')




                        # run "StartDb-<locale>"
                        started_times += 1
                        test_log_number += 1
                        test_log_name = "startdb"
                        result = self.regression_pg_startdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('startdb')


                        # run "ContribCheck-<locale>"
                        execute = "./buildclient_run_buildfarm_contrib-installcheck.sh" + " " + str(test_locale) + " " + str(started_times)
                        run = self.run_shell(execute)
                        test_log_number += 1
                        test_log_name = "contrib-installcheck"
                        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                          os.path.join(self.buildfarm_logs, 'contrib-install-check-' + str(test_locale) + '.log'))


                        # add logfiles
                        files_log = glob.glob(os.path.join(self.build_dir, 'contrib') + os.sep + '*' + os.sep + 'regression.diffs')
                        for file_log in files_log:
                            self.attach_logfile_pg_buildfarm(file_log,
                                                             os.path.join(self.buildfarm_logs, 'contrib-install-check-' + str(test_locale) + '.log'),
                                                             "\n\n================= " + file_log[len(self.build_dir) + 1:] + " ===================\n")
                            self.attach_logfile_buildfarm(file_log,
                                                          "tests", test_log_number, test_log_name,
                                                          file_log[len(self.build_dir) + 1:])

                        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                         os.path.join(self.buildfarm_logs, 'contrib-install-check-' + str(test_locale) + '.log'),
                                                         "\n\n================= logfile ===================\n")
                        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                      "tests", test_log_number, test_log_name,
                                                      "db logfile")


                        # add stack traces of any "core*" file found in the tree
                        stack_trace = self.stack_traces(os.path.join(self.install_dir, 'data-' + test_locale))
                        if (len(stack_trace) > 0):
                            f = open(os.path.join(self.buildfarm_logs, 'contrib-install-check-' + str(test_locale) + '.log'), 'a')
                            f.write(stack_trace)
                            f.close()
                            f = open(self.config.logfile_name("tests", file_type = 'logfile', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name), 'a')
                            f.write(stack_trace)
                            f.close()


                        # set mtime and other metadata to original timestamp from the test
                        self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                        os.path.join(self.buildfarm_logs, 'contrib-install-check-' + str(test_locale) + '.log'))

                        # finally deal with any error
                        if (run[0] > 0):
                            self.print_run_error(run, execute)
                            raise RegressionTestErrorPG('contrib-installcheck')


                        # run "StopDb-<locale>"
                        test_log_number += 1
                        test_log_name = "stopdb"
                        result = self.regression_pg_stopdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('stopdb')




                        # run "StartDb-<locale>"
                        started_times += 1
                        test_log_number += 1
                        test_log_name = "startdb"
                        result = self.regression_pg_startdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('startdb')


                        # run "TestModulesCheck-<locale>"
                        execute = "./buildclient_run_buildfarm_testmodules-installcheck.sh" + " " + str(test_locale) + " " + str(started_times)
                        run = self.run_shell(execute)
                        test_log_number += 1
                        test_log_name = "contrib-installcheck"
                        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                          os.path.join(self.buildfarm_logs, 'testmodules-install-check-' + str(test_locale) + '.log'))


                        # add logfiles
                        files_log = glob.glob(os.path.join(self.build_dir, 'src', 'test', 'modules') + os.sep + '*' + os.sep + 'regression.diffs')
                        for file_log in files_log:
                            self.attach_logfile_pg_buildfarm(file_log,
                                                             os.path.join(self.buildfarm_logs, 'testmodules-install-check-' + str(test_locale) + '.log'),
                                                             "\n\n================= " + file_log[len(self.build_dir) + 1:] + " ===================\n")
                            self.attach_logfile_buildfarm(file_log,
                                                          "tests", test_log_number, test_log_name,
                                                          file_log[len(self.build_dir) + 1:])

                        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                         os.path.join(self.buildfarm_logs, 'testmodules-install-check-' + str(test_locale) + '.log'),
                                                         "\n\n================= logfile ===================\n")
                        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                      "tests", test_log_number, test_log_name,
                                                      "db logfile")


                        # add stack traces of any "core*" file found in the tree
                        stack_trace = self.stack_traces(os.path.join(self.install_dir, 'data-' + test_locale))
                        if (len(stack_trace) > 0):
                            f = open(os.path.join(self.buildfarm_logs, 'testmodules-install-check-' + str(test_locale) + '.log'), 'a')
                            f.write(stack_trace)
                            f.close()
                            f = open(self.config.logfile_name("tests", file_type = 'logfile', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name), 'a')
                            f.write(stack_trace)
                            f.close()


                        # set mtime and other metadata to original timestamp from the test
                        self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                        os.path.join(self.buildfarm_logs, 'testmodules-install-check-' + str(test_locale) + '.log'))

                        # finally deal with any error
                        if (run[0] > 0):
                            self.print_run_error(run, execute)
                            raise RegressionTestErrorPG('contrib-installcheck')


                        # run "StopDb-<locale>"
                        test_log_number += 1
                        test_log_name = "stopdb"
                        result = self.regression_pg_stopdb(extra_options, log_data, test_locale, started_times, test_log_number, test_log_name)
                        if (result is False):
                            raise RegressionTestErrorPG('stopdb')



                    except RegressionTestErrorPG as error:
                        # shutdown everything
                        logging.info("shutting down everything after test failure")
                        execute = "./buildclient_run_buildfarm_stopdbs_after_failure.sh"
                        run = self.run_shell(execute)
                        # don't care about error handling
                        return False



                    # run "ECPG-Check-<locale>"
                    execute = "./buildclient_run_buildfarm_ecpg-check.sh"
                    run = self.run_shell(execute)
                    test_log_number += 1
                    test_log_name = "contrib-installcheck"
                    self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

                    self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                      os.path.join(self.buildfarm_logs, 'ecpg-check.log'))


                    # add logfiles
                    files_log = glob.glob(os.path.join(self.build_dir, 'src', 'interfaces', 'ecpg', 'test', 'log', 'regression.diffs'))
                    files_log.extend(glob.glob(os.path.join(self.build_dir, 'src', 'interfaces', 'ecpg', 'test', 'log') + os.sep + '*.log'))
                    for file_log in files_log:
                        self.attach_logfile_pg_buildfarm(file_log,
                                                         os.path.join(self.buildfarm_logs, 'ecpg-check.log'),
                                                         "\n\n================= " + file_log[len(self.build_dir) + 1:] + " ===================\n")
                        self.attach_logfile_buildfarm(file_log,
                                                      "tests", test_log_number, test_log_name,
                                                      file_log[len(self.build_dir) + 1:])

                    self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                     os.path.join(self.buildfarm_logs, 'ecpg-check.log'),
                                                     "\n\n================= logfile ===================\n")
                    self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                                  "tests", test_log_number, test_log_name,
                                                  "db logfile")


                    # add stack traces of any "core*" file found in the tree
                    stack_trace = self.stack_traces(os.path.join(self.build_dir, 'src', 'test', 'regress', 'tmp_check', 'data'))
                    if (len(stack_trace) > 0):
                        f = open(os.path.join(self.buildfarm_logs, 'ecpg-check.log'), 'a')
                        f.write(stack_trace)
                        f.close()
                        f = open(self.config.logfile_name("tests", file_type = 'logfile', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name), 'a')
                        f.write(stack_trace)
                        f.close()


                    # set mtime and other metadata to original timestamp from the test
                    self.copy_stats(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                    os.path.join(self.buildfarm_logs, 'ecpg-check.log'))

                    # finally deal with any error
                    if (run[0] > 0):
                        self.print_run_error(run, execute)
                        return False



        elif (repository_type == 'Greenplum'):
            # FIXME: figure out the hostfile, and check ssh connections to all hosts
            self.regression_logfile_directory = os.path.join(self.install_dir, "tmp_regression_tests", "gpAdminLogs")
            execute = "./buildclient_run_regression_tests.sh"
            run = self.run_shell(execute)
            self.dump_logs(self.build_dir, run, execute, "log_09_tests")
            log_data['run_tests'] = True
            log_data['extra_tests'] = extra_options
            log_data['result_tests'] = run[0]
            log_data['time_tests'] = run[2]
            if (run[0] > 0):
                self.print_run_error(run, execute, ' tests failed.')
                return False
            self.regression_logfile_directory = False

        logging.debug("regression tests completed")
        return True



    # copy_logfile()
    #
    # copy a specific logfile, keep the metadata intact
    #
    # parameter:
    #  - self
    #  - from filename
    #  - to filename
    # return:
    #  none
    def copy_logfile(self, from_file, to_file):
        # keep metadata (like mtime) intact, the PostgreSQL buildfarm depends on it
        if not (os.path.exists(from_file)):
            logging.error("copy_logfile: from file does not exist!")
            logging.error("file: " + str(from_file))
            sys.exit(1)
        shutil.copy2(from_file, to_file)



    # copy_stats()
    #
    # copy metadata from one file to another
    #
    # parameter:
    #  - self
    #  - from filename
    #  - to filename
    # return:
    #  none
    def copy_stats(self, from_file, to_file):
        # keep metadata (like mtime) intact, the PostgreSQL buildfarm depends on it
        if not (os.path.exists(from_file)):
            logging.error("copy_stats: from file does not exist!")
            logging.error("file: " + str(from_file))
            sys.exit(1)
        shutil.copystat(from_file, to_file)



    # attach_logfile_pg_buildfarm()
    #
    # attach a logfile to another file
    #
    # parameter:
    #  - self
    #  - logfile to attach
    #  - target logfile
    #  - header to insert
    #  - stats file: optional filename which metadata is used to update the target logfile
    #  - start position: optional start position in the attach logfile
    # return:
    #  none
    def attach_logfile_pg_buildfarm(self, log_file, to_file, header, stat_file = None, start_pos = None):
        if (os.path.exists(log_file)):
            f = open(to_file, 'a')
            f.write(header)
            # the PostgreSQL buildfarm makes no attempt to read files in binary mode
            r = open(log_file, 'r')
            if (start_pos is not None):
                r.seek(start_pos, 0)
            f.write(r.read())
            r.close()
            f.close()
            if (stat_file is not None):
                if not (os.path.exists(stat_file)):
                    logging.error("stat file does not exist!")
                    logging.error("file: " + str(stat_file))
                self.copy_stats(stat_file, to_file)



    # attach_logfile_buildfarm()
    #
    # attach a logfile to another file
    #
    # parameter:
    #  - self
    #  - logfile to attach
    #  - target logfile
    #  - header to insert
    #  - start position: optional start position in the attach logfile
    # return:
    #  none
    def attach_logfile_buildfarm(self, log_file, target_log_type, target_second_number, target_second_type, header, start_pos = None):
        if (os.path.exists(log_file)):

            # calculate to_file name
            to_file = self.config.logfile_name(target_log_type, second_number = target_second_number, second_type = target_second_type, file_type = "logfile", full_path = self.build_dir)
            if (os.path.exists(to_file)):
                to_file_size = os.stat(to_file).st_size
            else:
                to_file_size = 0

            f = open(to_file, 'a')
            if (to_file_size > 0):
                # add linebreaks if the file already has logs
                f.write(os.linesep + os.linesep)
            f.write("=" * 15 + " " + header + " " + "=" * 15 + os.linesep)
            r = open(log_file, 'r')
            if (start_pos is not None):
                r.seek(start_pos, 0)
            f.write(r.read())
            r.close()
            f.close()



    # regression_pg_initdb()
    #
    # initialize a test database
    #
    # parameter:
    #  - self
    #  - extra options
    #  - pointer to log data
    #  - locale string used to initialize the cluster
    #  - ongoing test number
    #  - test name
    # return:
    #  none
    def regression_pg_initdb(self, extra_options, log_data, test_locale, test_log_number, test_log_name):
        # run "Initdb-<locale>"
        execute = "./buildclient_run_buildfarm_initdb.sh" + " " + str(test_locale)
        run = self.run_shell(execute)
        test_log_name += "-" + str(test_locale)
        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                          os.path.join(self.buildfarm_logs, 'initdb-' + str(test_locale) + '.log'))

        # finally deal with any error
        if (run[0] > 0):
            self.print_run_error(run, execute)
            return False

        return True



    # regression_pg_startdb()
    #
    # initialize a test database
    #
    # parameter:
    #  - self
    #  - extra options
    #  - pointer to log data
    #  - locale string used to initialize the cluster
    #  - number times the database was started
    #  - ongoing test number
    #  - test name
    # return:
    #  none
    def regression_pg_startdb(self, extra_options, log_data, test_locale, started_times, test_log_number, test_log_name):
        # run "StartDb-<locale>"
        execute = "./buildclient_run_buildfarm_startdb.sh" + " " + str(test_locale) + " " + str(started_times)
        run = self.run_shell(execute)
        test_log_name += "-" + str(test_locale) + "-" + str(started_times)
        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                          os.path.join(self.buildfarm_logs, 'startdb-' + str(test_locale) + "-" + str(started_times) + '.log'))

        # add logfiles
        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                         os.path.join(self.buildfarm_logs, 'startdb-' + str(test_locale) + "-" + str(started_times) + '.log'),
                                         "========== db log file ==========",
                                         stat_file = self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name))
        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                      "tests", test_log_number, test_log_name,
                                      "db logfile")

        # finally deal with any error
        if (run[0] > 0):
            self.print_run_error(run, execute)
            return False

        return True



    # regression_pg_stopdb()
    #
    # initialize a test database
    #
    # parameter:
    #  - self
    #  - extra options
    #  - pointer to log data
    #  - locale string used to initialize the cluster
    #  - number times the database was started
    #  - ongoing test number
    #  - test name
    # return:
    #  none
    def regression_pg_stopdb(self, extra_options, log_data, test_locale, started_times, test_log_number, test_log_name):
        # run "StopDb-<locale>"
        lastpos = os.stat(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times))).st_size
        execute = "./buildclient_run_buildfarm_stopdb.sh" + " " + str(test_locale) + " " + str(started_times)
        run = self.run_shell(execute)
        test_log_name += "-" + str(test_locale) + "-" + str(started_times)
        self.dump_logs(self.build_dir, run, execute, self.config.logfile_name("tests", second_number = test_log_number, second_type = test_log_name))

        self.copy_logfile(self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                          os.path.join(self.buildfarm_logs, 'stopdb-' + str(test_locale) + "-" + str(started_times) + '.log'))

        # add logfiles
        self.attach_logfile_pg_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                         os.path.join(self.buildfarm_logs, 'stopdb-' + str(test_locale) + "-" + str(started_times) + '.log'),
                                         "========== db log file ==========",
                                         stat_file = self.config.logfile_name("tests", file_type = 'stdout_stderr', full_path = self.build_dir, second_number = test_log_number, second_type = test_log_name),
                                         start_pos = lastpos)
        self.attach_logfile_buildfarm(os.path.join(self.install_dir, 'logfile-' + str(test_locale) + "-" + str(started_times)),
                                      "tests", test_log_number, test_log_name,
                                      "db logfile", start_pos = lastpos)

        # finally deal with any error
        if (run[0] > 0):
            self.print_run_error(run, execute)
            return False

        return True



    # print_run_error()
    #
    # print out run error messages
    #
    # parameter:
    #  - self
    #  - list with result from run_shell()
    #  - arguments string
    #  - filter string for output
    # return:
    #  none
    def print_run_error(self, run, command, filter = False):
        print("")
        print("exec failed (return code: " + str(run[0]) + ")")
        if (len(run[1]) > 1):
            # scan first if the filter string is in the output
            if (filter is not False):
                filter_linenum = 0
                filter_found = False
                for line in run[1].decode().splitlines():
                    filter_linenum += 1
                    if (line.find(filter) != -1):
                        filter_found = filter_linenum
                        break
                if (filter_found is False):
                    # didn't find the filter string
                    filter = False

            if (filter is False):
                print("stdout/stderr:")
                #print(run[1])
                print("------------------------------------------")
                print("\n".join(run[1].decode().splitlines()[-20:]))
                print("------------------------------------------")
                print("")
            else:
                print("stdout/stderr:")
                #print(run[1])
                print("------------------------------------------")
                print("\n".join(run[1].splitlines()[(filter_linenum - 10):(filter_linenum + 10)].decode()))
                print("------------------------------------------")
                print("")
        print("failing command:")
        print(command)

        if (self.config.get('disable-support') is False):
            logging.debug("generate support package")
            support_dir = self.config.get('support-dir')
            support_file = self.config.get('support-file')
            if (len(support_file) > 0):
                support_archive_name = support_file
            elif (len(support_dir) > 0):
                tmp1, tmp2 = os.path.split(self.build_dir + "." + self.config.get('support-archive-type') + "")
                support_archive_name = os.path.join(support_dir, tmp2)
            else:
                support_archive_name = self.build_dir + "." + self.config.get('support-archive-type') + ""
            execute = "'" + self.config.get('support-bin') + "' --archive-name='" + support_archive_name + "' --archive-type='" + self.config.get('support-archive-type') + "'"
            if (self.regression_logfile_directory is not False):
                # include all logfiles from the separate logfile directory
                execute += " --logfile '" + self.regression_logfile_directory + "'"
            run = self.run_shell(execute)
            if (run[0] > 0):
                logging.error("Error generating support package")
            else:
                logging.info("Support package: " + support_archive_name)
                self.add_support_archive(support_archive_name)

        self.add_entry_to_delete_error(self.build_dir)
        if (self.install_dir != False):
            self.add_entry_to_delete_error(self.install_dir)



    # run_shell()
    #
    # run an arbitrary shell command
    #
    # parameter:
    #  - self
    #  - string with command and arguments
    # return:
    #  - list with:
    #    - exit code
    #    - content of STDOUT
    #    - content of STDERR
    def run_shell(self, arguments):
        dir = self.build_dir

        call = shlex.split(arguments)
        #print("call: " + str(call))
        #return [1, '', '']

        logging.debug(str(call))
        t_start = datetime.datetime.now()
        # use extra environment which enables ccache
        proc = Popen(call, stdout=PIPE, stderr=subprocess.STDOUT, cwd=dir, env=self.create_env_for_ccache())
        out, err = proc.communicate()
        exitcode = proc.returncode
        t_end = datetime.datetime.now()
        t_run = "%.2f" % (t_end - t_start).total_seconds()
        logging.debug("runtime: " + str(t_run) + "s")

        return [exitcode, out, t_run]



    # dump_logs()
    #
    # dump logfiles into build directory
    #
    # parameter:
    #  - self
    #  - build directory
    #  - result from run_shell()
    #  - arguments sent to run_shell()
    #  - template for resulting filename
    # return:
    #  none
    def dump_logs(self, build_dir, run, args, template):
        f = open(os.path.join(build_dir, template + '_exit_code.txt'), 'w')
        f.write(str(run[0]) + os.linesep)
        f.close()
        f = open(os.path.join(build_dir, template + '_stdout_stderr.txt'), 'w')
        f.write(run[1].decode() + os.linesep)
        f.close()
        f = open(os.path.join(build_dir, template + '_cmdline.txt'), 'w')
        f.write(args + os.linesep)
        f.close()



    # create_env_for_ccache()
    #
    # populate a copy of he shell environment with ccache settings
    #
    # parameter:
    #  - self
    # return:
    #  - environment copy
    def create_env_for_ccache(self):
        env = os.environ.copy()

        if (len(self.config.get('ccache-bin')) > 0):
            # for now just assume it's 'gcc' and 'g++'
            # was told that clang on Mac links to these names as well
            env['CC'] = self.config.get('ccache-bin') + ' gcc'
            env['CXX'] = self.config.get('ccache-bin') + ' g++'

        return env



    # stack_traces()
    #
    # generate stack traces of all core files
    #
    # parameter:
    #  - self
    #  - directory to scan for core files
    # return:
    #  - string with stack traces
    def stack_traces(self, scan_dir):
        # first check if there is a gdb binary in $PATH

        gdb = self.config.find_in_path('gdb')
        if (gdb is False):
            return None

        trace = ''

        for core_dirpath, core_dirs, core_files in os.walk(scan_dir):
            for core_file in core_files:
                if (core_file[0:4] == 'core'):
                    core_this = os.path.join(core_dirpath, core_file)
                    core_trace = self.stack_trace(core_this, scan_dir, gdb)
                    if (core_trace is not None):
                        trace += core_trace

        return trace



    # stack_trace()
    #
    # generate a stack trace for a core file
    #
    # parameter:
    #  - self
    #  - core file name
    #  - directory name
    #  - path to gdb binary
    # return:
    #  - string with stack traces
    def stack_trace(self, core, scan_dir, gdb):
        gpdcmd = os.path.join(scan_dir, 'gdbcmd')
        f.open(gpdcmd, 'w')
        f.write("bt" + os.linesep)
        f.close()

        execute = gdb + " -x " + gpdcmd + " --batch " + os.path.join(self.install_dir, 'bin', 'postgres') + "'" + core + "'"
        run = self.run_shell(execute)
        if (run[0] > 0):
            # something happened, cannot extract stack trace
            return None

        os.remove(gpdcmd)

        trace = "\n\n" + "=" * 15 + " stack trace: "
        trace += core[len(scan_dir) + 1:]
        trace += " " + "=" * 15 + "\n"
        trace += run[1]

        return trace
