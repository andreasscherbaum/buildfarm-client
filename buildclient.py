#!/usr/bin/env python
#
# Buildfarm client for PostgreSQL and Greenplum
#
# written by: Andreas Scherbaum <ascherbaum@pivotal.io>
#             Andreas Scherbaum <ads@pgug.de>
#

import re
import os
import sys
import logging
import tempfile
import atexit
import shutil
import time
import subprocess
from subprocess import Popen
import socket
import sqlite3
import datetime
from time import gmtime, localtime, strftime
# config functions
from config import Config
# repository functions
from repository import Repository
from build import Build
from patch import Patch
from database import Database
from buildfarm import Buildfarm
import copy


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
    # do something in the end ...
    pass

# register exit handler
atexit.register(exit_handler)







#######################################################################
# main code



config = Config()
config.parse_parameters()
config.load_config()
config.build_and_verify_config()
config.cleanup_old_dirs_and_files()

database = Database(config)
all_log_data = database.init_dataset()





# FIXME: provide option for a user-defined cluster setup
# hostfile and gpinitsystem file

# FIXME: optional clone from the original repository, not creating a detached copy

# FIXME: Orca (for Greenplum only)

# FIXME: random ports for regression tests
# FIXME: check if socket files still exist (any of them) after the test, emit a warning

# FIXME: files changed since last run
# FIXME: revisions since last run

# FIXME: delete log entry, entries (1, 2, 3, 4-6)
# FIXME: delete job entries

# FIXME: catch if the directory for the lockfile is not writable, or does not exist


# add more env keys, see run_build.pl (around line 60)



# run_extra_targets
# test_locales




#######################################################################
# list results of previous runs, in compact mode
if (config.get('list-results') is True):
    data = database.fetch_all_from_build_status()
    print("")
    if (data is None or len(data) == 0):
        print("No previous records in database")
        print("")
        sys.exit(0)

    if (len(data) > 1):
        print("" + str(len(data)) + " records found")
    else:
        print("1 record found")
    print("")

    for i in data:
        tmp_id = i['id']
        tmp_repository = i['repository']
        tmp_repository_type = i['repository_type']
        tmp_branch = i['branch']
        tmp_revision = i['revision']
        tmp_start_time_local = i['start_time_local']
        status = []
        if (i['is_head'] == 1):
            status.append('head')
        if (i['is_buildfarm'] == 1):
            status.append('buildfarm')
        if (i['orca'] == 1):
            status.append('orca')
        if (i['extra_patches'] == 1):
            status.append('patches')
        if (i['run_git_update'] == 1):
            status.append('update')
        if (i['run_configure'] == 1):
            status.append('configure')
        if (i['run_make'] == 1):
            status.append('make')
        if (i['run_install'] == 1):
            status.append('install')
        if (i['run_tests'] == 1):
            status.append('tests')
        if (i['run_extra_targets'] == 1):
            status.append('extra targets')
        if (len(i['test_locales']) > 0):
            status.append('locales')
        error = 'OK'
        if (i['run_git_update'] == 1 and i['result_git_update'] > 0):
            error = 'ERROR'
        if (i['run_configure'] == 1 and i['result_configure'] > 0):
            error = 'ERROR'
        if (i['run_make'] == 1 and i['result_make'] > 0):
            error = 'ERROR'
        if (i['run_install'] == 1 and i['result_install'] > 0):
            error = 'ERROR'
        if (i['run_tests'] == 1 and i['result_tests'] > 0):
            error = 'ERROR'
        if (i['result_portcheck'] is not None and i['result_portcheck'] > 0):
            error = 'ERROR'
        if (i['result_portcheck'] is None and i['is_buildfarm'] == 1 and i['run_configure'] == 1):
            # buildfarm mode requires running regression tests
            error = 'ERROR'
        if (i['result_portcheck'] is None and i['run_tests'] == 1):
            # running regression tests requires running portcheck
            error = 'ERROR'

        if (tmp_repository_type is None):
            tmp_repository_type = '?'
        if (tmp_revision is None):
            tmp_revision = '?'
        if (tmp_branch is None):
            tmp_branch = '?'

        print("{0:5d}:  {1:s}  {2:5s}  {3:s} / {4:s}  ({5:s})  ({6:s} / {7:s})".format(tmp_id, tmp_start_time_local.replace('_', ' '), error, str(tmp_branch), str(tmp_revision), '/'.join(status), tmp_repository, tmp_repository_type))
    print("")
    sys.exit(0)



#######################################################################
# show full result of a previous run
if (len(config.get('show-result')) > 0):
    if (config.get('show-result') == 'latest' or config.get('show-result') == 'last'):
        logging.debug("looking up latest result")
        data = database.fetch_last_build_status_id()
        if (str(data['id']) == 'not set'):
            logging.error("No entries in database!")
            sys.exit(1)
        logging.debug("last result has id: " + str(data['id']))
        config.set('show-result', str(data['id']))
    logging.debug("show one result: " + config.get('show-result'))
    try:
        id = int(config.get('show-result'))
    except ValueError:
        logging.error("Not a number: " + str(config.get('show-result')))
        sys.exit(1)
    if (id <= 0):
        logging.error("Invalid ID: " + str(id))
        sys.exit(1)

    data = database.fetch_specific_build_status(id)
    if (data is None or len(data) == 0):
        print("")
        print("Record '" + config.get('show-result') + "' does not exist!")
        print("")
        sys.exit(1)

    print("")
    print("{:>17}:  {:s}".format("ID", str(data['id'])))
    print("{:>17}:  {:s}".format("Time", str(data['start_time'])))
    print("{:>17}:  {:s}".format("Time", str(data['start_time_local'].replace('_', ' '))))

    print("")

    print("{:>17}:  {:s}".format("Repository", str(data['repository'])))
    if (data['repository_type'] is None):
        print("{:>17}:  {:s}".format("Repository Type", 'n/a'))
    else:
        print("{:>17}:  {:s}".format("Repository Type", str(data['repository_type'])))

    if (data['branch'] is None):
        print("{:>17}:  {:s}".format("Branch", 'n/a'))
    else:
        print("{:>17}:  {:s}".format("Branch", str(data['branch'])))

    if (data['revision'] is None):
        print("{:>17}:  {:s}".format("Revision", 'n/a'))
    else:
        print("{:>17}:  {:s}".format("Revision", str(data['revision'])))

    if (data['is_head'] is None):
        print("{:>17}:  {:s}".format("is HEAD", 'n/a'))
    elif (data['is_head'] == 1):
        print("{:>17}:  {:s}".format("is HEAD", "yes"))
    else:
        print("{:>17}:  {:s}".format("is HEAD", "no"))

    if (data['orca'] == 1):
        print("{:>17}:  {:s}".format("Orca", "yes"))
    #elif (data['orca'] is None):
    #    print("{:>17}:  {:s}".format("Orca", 'n/a'))
    #else:
    #    print("{:>17}:  {:s}".format("Orca", "no"))

    print("")

    print("{:>17}:  {:s}".format("Run git update", str(data['run_git_update'])))
    print("{:>17}:  {:s}".format("Run configure", str(data['run_configure'])))
    print("{:>17}:  {:s}".format("Run make", str(data['run_make'])))
    print("{:>17}:  {:s}".format("Run install", str(data['run_install'])))
    print("{:>17}:  {:s}".format("Run tests", str(data['run_tests'])))
    if (len(str(data['run_extra_targets'])) > 0):
        print("{:>17}:  {:s}".format("Run extra targets", str(data['run_extra_targets'])))
    if (len(str(data['extra_patches'])) > 0):
        print("{:>17}:  {:s}".format("Extra patches", str(data['extra_patches'])))

    print("")

    if (data['result_portcheck'] is None):
        print("{:>17}:  {:s}".format("Result portcheck", 'n/a'))
    elif (data['result_portcheck'] == 0):
        print("{:>17}:  {:s}".format("Result portcheck", 'OK'))
    else:
        print("{:>17}:  {:s}".format("Result portcheck", 'Error'))

    if (data['result_git_update'] is None):
        print("{:>17}:  {:s}".format("Result git update", 'n/a'))
    elif (data['result_git_update'] == 0):
        print("{:>17}:  {:s}".format("Result git update", 'OK'))
    else:
        print("{:>17}:  {:s}".format("Result git update", str(data['result_git_update'])))

    if (data['result_configure'] is None):
        print("{:>17}:  {:s}".format("Result configure", 'n/a'))
    elif (data['result_configure'] == 0):
        print("{:>17}:  {:s}".format("Result configure", 'OK'))
    else:
        print("{:>17}:  {:s}".format("Result configure", str(data['result_configure'])))

    if (data['result_make'] is None):
        print("{:>17}:  {:s}".format("Result make", 'n/a'))
    elif (data['result_make'] == 0):
        print("{:>17}:  {:s}".format("Result make", 'OK'))
    else:
        print("{:>17}:  {:s}".format("Result make", str(data['result_make'])))

    if (data['result_install'] is None):
        print("{:>17}:  {:s}".format("Result install", 'n/a'))
    elif (data['result_install'] == 0):
        print("{:>17}:  {:s}".format("Result install", 'OK'))
    else:
        print("{:>17}:  {:s}".format("Result install", str(data['result_install'])))

    if (data['result_tests'] is None):
        print("{:>17}:  {:s}".format("Result tests", 'n/a'))
    elif (data['result_tests'] == 0):
        print("{:>17}:  {:s}".format("Result tests", 'OK'))
    else:
        print("{:>17}:  {:s}".format("Result tests", str(data['result_tests'])))

    print("")

    print("{:>17}:  {:s}".format("Time git update", str(data['time_git_update'])))
    print("{:>17}:  {:s}".format("Time configure", str(data['time_configure'])))
    print("{:>17}:  {:s}".format("Time make", str(data['time_make'])))
    print("{:>17}:  {:s}".format("Time install", str(data['time_install'])))
    print("{:>17}:  {:s}".format("Time tests", str(data['time_tests'])))

    print("")

    print("{:>17}:  {:s}".format("Extra configure", str(data['extra_configure'])))
    print("{:>17}:  {:s}".format("Extra make", str(data['extra_make'])))
    print("{:>17}:  {:s}".format("Extra install", str(data['extra_install'])))
    print("{:>17}:  {:s}".format("Extra tests", str(data['extra_tests'])))

    # list additional patches
    if (len(str(data['patches'])) > 0):
        print("")
        patches = str(data['patches']).split('|')
        for patch in patches:
            print("{:>17}:  {:s}".format("Extra patch", patch))

    # list locales
    if (len(str(data['test_locales'])) > 0):
        print("{:>17}:  {:s}".format("Locales", str(data['test_locales'])))

    if (len(data['errorstr']) > 0):
        print("")
        print("{:>17}:  {:s}".format("Error", data['errorstr']))

    print("")

    sys.exit(0)



#######################################################################
# show the list of pending or finished jobs, then exit
if (config.get('list-jobs') is True or config.get('list-all-jobs') is True):
    if (config.get('list-jobs') is True):
        jobs = database.list_pending_buildfarm_jobs()
    elif (config.get('list-all-jobs') is True):
        jobs = database.list_all_buildfarm_jobs()
    else:
        logging.error("internal error")
        sys.exit(1)
    if (jobs is None or len(jobs) == 0):
        print("")
        if (config.get('list-jobs') is True):
            print("No pending buildfarm jobs!")
        if (config.get('list-all-jobs') is True):
            print("No buildfarm jobs!")
        print("")
        sys.exit(0)

    for job in jobs:
        print("")
        print("{:>13}:  {:s}".format("ID", str(job['id'])))
        if (config.get('list-all-jobs') is True):
            if (job['finished'] == 1):
                print("{:>13}:  {:s}".format("pending", 'no'))
            else:
                print("{:>13}:  {:s}".format("pending", 'yes'))
        time_added = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(job['added_ts'])))
        print("{:>13}:  {:s}".format("Time added", str(time_added)))
        if (job['executed_ts'] > 0):
            time_executed = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(job['executed_ts'])))
            print("{:>13}:  {:s}".format("Time executed", str(time_executed)))
        print("{:>13}:  {:s}".format("Repository", str(job['repository'])))
        print("{:>13}:  {:s}".format("Branch", str(job['branch'])))
        print("{:>13}:  {:s}".format("Revision", str(job['revision'])))

        if (job['is_head'] == 1):
            print("{:>13}:  {:s}".format("is HEAD", "yes"))
        else:
            print("{:>13}:  {:s}".format("is HEAD", "no"))

        if (job['orca'] == 1):
            print("{:>13}:  {:s}".format("Orca", "yes"))

        if (len(job['extra_configure']) > 0):
            print("{:>13}:  {:s}".format("extra configure", str(job['extra_configure'])))
        if (len(job['extra_make']) > 0):
            print("{:>13}:  {:s}".format("extra make", str(job['extra_make'])))
        if (len(job['extra_install']) > 0):
            print("{:>13}:  {:s}".format("extra install", str(job['extra_install'])))
        if (len(job['extra_tests']) > 0):
            print("{:>13}:  {:s}".format("extra tests", str(job['extra_tests'])))
        if (len(job['extra_tests']) > 0):
            print("{:>13}:  {:s}".format("extra tests", str(job['extra_tests'])))
        if (len(job['run_extra_targets']) > 0):
            print("{:>13}:  {:s}".format("extra targets", str(job['run_extra_targets'])))
        if (len(job['test_locales']) > 0):
            print("{:>13}:  {:s}".format("locales", str(job['test_locales'])))
        print("")

    sys.exit(0)



#######################################################################
# buildfarm mode, requeue a finished or pending job
if (len(config.get('requeue-job')) > 0):
    logging.debug("requeue buildfarm job: " + config.get('requeue-job'))
    try:
        id = int(config.get('requeue-job'))
    except ValueError:
        logging.error("Not a number: " + str(config.get('requeue-job')))
        sys.exit(1)
    if (id <= 0):
        logging.error("Invalid ID: " + str(id))
        sys.exit(1)

    data = database.fetch_specific_buildfarm_job(id)
    if (data is None or len(data) == 0):
        print("")
        print("Record '" + config.get('requeue-job') + "' does not exist!")
        print("")
        sys.exit(1)

    database.update_buildfarm_job_requeued(id)
    print("")
    print("Job '" + config.get('requeue-job') + "' requeued")
    print("")
    sys.exit(0)



#######################################################################
# buildfarm mode, create jobs
if (config.get('buildfarm') is True):
    logging.debug("buildfarm mode: create new jobs")
    if (len(config.get('repository-url')) == 0):
        logging.error("Error: No repository url specified")
        sys.exit(1)

    log_data = copy.deepcopy(all_log_data)
    log_data['is_buildfarm'] = True
    log_data['repository'] = config.get('repository-url')
    log_data['start_time'] = int(time.time())
    current_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(log_data['start_time']))
    log_data['start_time_local'] = current_time

    # from here on, only one repository is possible
    # create a repository instance
    repository = Repository(config, database, config.get('repository-url'), config.get('cache-dir'))
    repository.handle_update(True, log_data)
    # from here on a local copy of the repository is available

    # create a list of all jobs
    jobs = []
    for branch in config.get('build-branch'):
        job = {}
        job['added_ts'] = int(time.time())
        job['repository'] = config.get('repository-url')
        job['repository_type'] = repository.repository_type
        job['branch'] = branch
        if (config.get('build-revision') == 'HEAD'):
            job['revision'] = repository.repository_head(repository.full_path, branch)
            job['is_head'] = True
        else:
            job['revision'] = config.get('build-revision')
            job['is_head'] = False

        job['extra-configure'] = config.get('extra-configure')
        job['extra-make'] = config.get('extra-make')
        job['extra-install'] = config.get('extra-install')
        job['extra-tests'] = config.get('extra-tests')
        job['run-extra-targets'] = config.get('test-extra-targets')
        job['test-locales'] = config.get('test-locales')

        # create one job with Orca=off in any case, just to ensure that we test this case
        job['orca'] = False
        jobs.append(job)
        if (config.get('enable-orca') is True):
            # if Orca is enabled, create another job with Orca=on
            job['orca'] = False
            jobs.append(job)


    # figure out if this combination was built before
    # this only checks if this combination is in the job table for the buildfarm
    # it does not take into account if the job is already finished
    for job in jobs:
        if (database.buildfarm_job_exists(job['repository'], job['branch'], job['revision'], job['extra-configure'],
                                          job['extra-make'], job['extra-install'], job['extra-tests'],
                                          job['run-extra-targets'], job['test-locales'],
                                          orca = job['orca']) is False):
            # not found, add this job to the queue
            logging.info("add to buildfarm queue: " + job['branch'] + " / " + job['revision'])
            database.add_bildfarm_job(job)

    # write log entry into database
    database.log_build(log_data)

    if (config.get('add-jobs-only') is True):
        logging.debug("only add new jobs, exit")
        sys.exit(0)


#######################################################################
# buildfarm mode, execute jobs
if (config.get('buildfarm') is True):
    logging.debug("buildfarm mode: execute pending jobs")
    stats_jobs_executed = 0
    stats_jobs_successful = 0
    stats_jobs_delayed = 0
    while True:
        # loop until the job table has no more pending entries
        # it is possible that --add-jobs-only adds more jobs while this here is running
        jobs = database.list_pending_buildfarm_jobs()
        if (len(jobs) == 0):
            logging.info("no pending jobs")
            break

        # note: from here on, every job can have a different repository
        job_number = 0
        for job in jobs:
            log_data = copy.deepcopy(all_log_data)
            job_number += 1
            stats_jobs_executed += 1
            logging.debug("run buildfarm job: " + str(job['id']) + " (" + str(job_number) + " out of " + str(len(jobs)) + ")")
            # a local copy of the repository was created when the job was created
            # handle_update(False, ...) will ensure that the directory is still there
            log_data['repository'] = job['repository']
            log_data['branch'] = job['branch']
            # the correct revision was extracted when the job was created
            # it does not necessary mean that it is still the HEAD of the branch
            log_data['revision'] = job['revision']
            # copy this flag from the job, for logging purposes
            log_data['is_head'] = job['is_head']

            log_data['orca'] = job['orca']
            log_data['extra_configure'] = job['extra_configure']
            log_data['extra_make'] = job['extra_make']
            log_data['extra_install'] = job['extra_install']
            log_data['extra_tests'] = job['extra_tests']
            log_data['run_extra_targets'] = job['run_extra_targets']
            log_data['test_locales'] = job['test_locales']

            log_data['start_time'] = int(time.time())
            current_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(log_data['start_time']))
            log_data['start_time_local'] = current_time
            log_data['is_buildfarm'] = True


            # create a repository instance
            repository = Repository(config, database, log_data['repository'], config.get('cache-dir'))
            # do not update the repository again, assume that all necessary updates were fetched during job creation
            repository.handle_update(False, log_data)
            # from here on a local copy of the repository is available

            log_data['repository_type'] = repository.identify_repository_type(repository.full_path)

            logging.info("repository: " + log_data['repository'])
            if (log_data['is_head'] == 1):
                logging.info("building branch/revision: " + log_data['branch'] + '/' + log_data['revision'] + ' (HEAD)')
            else:
                logging.info("building branch/revision: " + log_data['branch'] + '/' + log_data['revision'])


            build_dir_name = str(current_time).replace('-', '') + '_bf_' + log_data['branch']

            # the config module ensures that all necessary --run-* options are set
            build_dir = repository.copy_repository(build_dir_name, log_data['branch'], log_data['revision'])

            build = Build(config, repository, build_dir)

            # test if ports for regression tests are available
            if (build.portcheck(log_data['repository_type'], log_data) is True):

                result_configure = build.run_configure(log_data['extra_configure'], build_dir_name, log_data)
                build.add_entry_to_delete_clean(build_dir)
                # FIXME: Orca


                if (result_configure is True):
                    result_make = build.run_make(log_data['extra_make'], log_data)

                    if (result_make is True):
                        install_dir = build.run_make_install(log_data['extra_install'], log_data, log_data['extra_make'])
                        if (install_dir is not False):
                            build.add_entry_to_delete_clean(install_dir)

                        if (install_dir is not False):
                            result_tests = build.run_tests(log_data['extra_tests'], log_data)
                            if (result_tests is not False):
                                stats_jobs_successful += 1

                # mark job as finished, regardless of the result
                database.update_buildfarm_job_finished(job['id'], log_data['start_time'])
            else:
                # mark job as delayed
                stats_jobs_delayed += 1
                database.update_buildfarm_job_delayed(job['id'], log_data['start_time'])

            # write log entry into database
            database.log_build(log_data)
            # gather data for buildfarm website
            buildfarm = Buildfarm(config, repository, build_dir, database)
            buildfarm.send_results(log_data)

    if (stats_jobs_executed > 0):
        logging.info("  jobs executed: " + str(stats_jobs_executed))
    if (stats_jobs_successful > 0):
        logging.info("jobs successful: " + str(stats_jobs_successful))
    if ((stats_jobs_executed - stats_jobs_successful - stats_jobs_delayed) > 0):
        logging.info("    jobs failed: " + str(stats_jobs_executed - stats_jobs_successful - stats_jobs_delayed))
    if (stats_jobs_delayed > 0):
        logging.info("   jobs delayed: " + str(stats_jobs_delayed))

    sys.exit(0)



#######################################################################
# manual mode
for branch in config.get('build-branch'):
    log_data = copy.deepcopy(all_log_data)
    log_data['repository'] = config.get('repository-url')
    log_data['branch'] = branch
    log_data['start_time'] = int(time.time())
    current_time = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(log_data['start_time']))
    log_data['start_time_local'] = current_time
    log_data['is_buildfarm'] = False
    if (config.get('build-revision') == 'HEAD'):
        log_data['is_head'] = True
    else:
        log_data['is_head'] = False

    # create a repository instance
    repository = Repository(config, database, config.get('repository-url'), config.get('cache-dir'))
    repository.handle_update(config.get('run-update'), log_data)
    # from here on a local copy of the repository is available

    log_data['repository_type'] = repository.identify_repository_type(repository.full_path)
    if (config.get('build-revision') == 'HEAD'):
        head = repository.repository_head(repository.full_path, branch)
        logging.info("branch/revision: " + branch + '/' + head + ' (' + config.get('build-revision') + ')')
        log_data['revision'] = head
    else:
        logging.info("branch/revision: " + branch + '/' + config.get('build-revision'))
        log_data['revision'] = config.get('build-revision')
    # use the current timestamp and the branch name as build dir name
    build_dir_name = str(current_time) + '_' + branch
    if (config.get('build-revision') != 'HEAD'):
        # add the revision name, if it's not HEAD
        build_dir_name += '_' + config.get('build-revision')
    if (config.get('run-configure') is True):

        # create "Patch" instance before creating the repository
        # https://github.com/andreasscherbaum/buildfarm-client/issues/1
        patch = Patch(config.get('patch'), config, repository, None, config.get('cache-dir'))
        if (patch.have_patches() is True):
            # retrieve all patches
            result_retrieve_patches = patch.retrieve_patches()
            log_data['patches'] = '|'.join(patch.patches)
            if (result_retrieve_patches is False):
                # retrieving patches failed, don't bother with the rest of the job
                # continue with next branch in list
                # don't care about logging, this is manual mode
                continue

        build_dir = repository.copy_repository(build_dir_name, branch, config.get('build-revision'))
        # the "Patch" instance is initialized without the build_dir information
        patch.set_build_dir(build_dir)

        if (patch.have_patches() is True):
            # patches are already retrieved - error is checked above
            result_apply_patches = patch.apply_patches()
            if (result_apply_patches is False):
                # continue with next branch in list
                # don't care about logging, this is manual mode
                continue

        build = Build(config, repository, build_dir)

        if (patch.have_patches() is True):
            log_data['extra_patches'] = True
            patch.remove_patches_after_build(build)

        # test if ports for regression tests are available
        # only check if regression tests will run later
        if (config.get('run-tests') is False or (config.get('run-tests') is True and build.portcheck(log_data['repository_type'], log_data) is True)):

            result_configure = build.run_configure(config.get('extra-configure'), build_dir_name, log_data)
            build.add_entry_to_delete_clean(build_dir)
            # FIXME: Orca


            if (result_configure is True and config.get('run-make') is True):
                result_make = build.run_make(config.get('extra-make'), log_data)

                if (result_make is True and config.get('run-install') is True):
                    install_dir = build.run_make_install(config.get('extra-install'), log_data, config.get('extra-make'))
                    if (install_dir is not False):
                        build.add_entry_to_delete_clean(install_dir)

                    if (install_dir is not False and config.get('run-tests') is True):
                        result_tests = build.run_tests(config.get('extra-tests'), log_data)


    # write log entry into database
    database.log_build(log_data)



sys.exit(0)
