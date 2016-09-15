import re
import os
import sys
import logging
import string
import sqlite3
import datetime
import atexit
import copy
import time


class Database:

    def __init__(self, config):
        self.config = config

        # database defaults to a hardcoded file
        self.connection = sqlite3.connect(os.path.join(os.environ.get('HOME'), '.buildclient'))
        self.connection.row_factory = sqlite3.Row
        # debugging
        #self.drop_tables()
        self.init_tables()
        #sys.exit(0);

        atexit.register(self.exit_handler)



    def exit_handler(self):
        self.connection.close()



    # init_dataset()
    #
    # initialize a dataset for later use
    #
    # parameter:
    #  - self
    # return:
    #  - object with all fields initialized
    def init_dataset(self):
        data = {}
        data['repository'] = None
        data['repository_type'] = None
        data['branch'] = None
        data['revision'] = None
        data['is_head'] = None

        data['start_time'] = None
        data['start_time_local'] = None
        data['orca'] = None
        data['is_buildfarm'] = None

        data['run_git_update'] = False
        data['run_configure'] = False
        data['run_make'] = False
        data['run_install'] = False
        data['run_tests'] = False
        data['run_extra_targets'] = ''

        data['time_git_update'] = 0
        data['time_configure'] = 0
        data['time_make'] = 0
        data['time_install'] = 0
        data['time_tests'] = 0
        data['times_buildfarm'] = []
        data['steps_buildfarm'] = []

        data['result_portcheck'] = None
        data['result_git_update'] = None
        data['result_configure'] = None
        data['result_make'] = None
        data['result_install'] = None
        data['result_tests'] = None

        data['extra_configure'] = ''
        data['extra_make'] = ''
        data['extra_install'] = ''
        data['extra_tests'] = ''
        data['extra_patches'] = False
        data['test_locales'] = ''
        data['patches'] = ''
        data['errorstr'] = ''

        data['pg_majorversion'] = None
        data['pg_version'] = None
        data['pg_version_num'] = None
        data['pg_version_str'] = None
        data['gp_majorversion'] = None
        data['gp_version'] = None
        data['gp_version_num'] = None

        return data



    # log_build()
    #
    # write a log entry
    #
    # parameter:
    #  - self
    #  - log data object
    # return:
    #  none
    def log_build(self, data_in):
        # create a copy, because we modify the content
        data = copy.deepcopy(data_in)
        #if (data['is_head'] is not True and data['is_head'] is not False):
        #    logging.error("'is_head' must be True or False")
        #    sys.exit(1)
        if (data['is_buildfarm'] is not True and data['is_buildfarm'] is not False):
            logging.error("'is_buildfarm' must be True or False")
            sys.exit(1)

        #if (data['is_head'] is True):
        #    data['is_head'] = 1
        #else:
        #    data['is_head'] = 0

        if (data['is_buildfarm'] is True):
            data['is_buildfarm'] = 1
        else:
            data['is_buildfarm'] = 0

        #if (data['orca'] is True):
        #    data['orca'] = 1
        #else:
        #    data['orca'] = 0

        if (data['run_git_update'] is True):
            data['run_git_update'] = 1
        else:
            data['run_git_update'] = 0

        if (data['run_configure'] is True):
            data['run_configure'] = 1
        else:
            data['run_configure'] = 0

        if (data['run_make'] is True):
            data['run_make'] = 1
        else:
            data['run_make'] = 0

        if (data['run_install'] is True):
            data['run_install'] = 1
        else:
            data['run_install'] = 0

        if (data['run_tests'] is True):
            data['run_tests'] = 1
        else:
            data['run_tests'] = 0

        if (data['extra_patches'] is True):
            data['extra_patches'] = 1
        else:
            data['extra_patches'] = 0

        #print("write repository_type: " + str(data['repository_type']))
        query = """INSERT INTO build_status
                               (repository, repository_type, branch, revision, is_head, is_buildfarm, start_time, start_time_local,
                                run_git_update, run_configure, run_make, run_install, run_tests,
                                time_git_update, time_configure, time_make, time_install, time_tests,
                                result_configure, result_make, result_install, result_tests,
                                extra_configure, extra_make, extra_install, extra_tests,
                                extra_patches, orca, patches, errorstr, result_portcheck, result_git_update,
                                run_extra_targets, test_locales,
                                pg_majorversion, pg_version, pg_version_num, pg_version_str,
                                gp_majorversion, gp_version, gp_version_num,
                                times_buildfarm, steps_buildfarm)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

        param = [data['repository'], data['repository_type'], data['branch'], data['revision'], data['is_head'], data['is_buildfarm'], data['start_time'], data['start_time_local'],
                 data['run_git_update'], data['run_configure'], data['run_make'], data['run_install'], data['run_tests'],
                 data['time_git_update'], data['time_configure'], data['time_make'], data['time_install'], data['time_tests'],
                 data['result_configure'], data['result_make'], data['result_install'], data['result_tests'],
                 data['extra_configure'], data['extra_make'], data['extra_install'], data['extra_tests'],
                 data['extra_patches'], data['orca'], data['patches'], data['errorstr'], data['result_portcheck'], data['result_git_update'],
                 data['run_extra_targets'], data['test_locales'],
                 data['pg_majorversion'], data['pg_version'], data['pg_version_num'], data['pg_version_str'],
                 data['gp_majorversion'], data['gp_version'], data['gp_version_num'],
                 "!".join(data['times_buildfarm']), " ".join(data['steps_buildfarm'])]

        self.execute_one(query, param)



    # init_tables()
    #
    # initialize all missing tables
    #
    # parameter:
    #  - self
    # return:
    #  none
    def init_tables(self):
        if (self.table_exist('build_status') is False):
            logging.debug("need to create table build_status")
            self.table_build_status()

        if (self.table_exist('buildfarm_jobs') is False):
            logging.debug("need to create table buildfarm_jobs")
            self.table_buildfarm_jobs()

        if (self.table_exist('buildfarm_postgresql') is False):
            logging.debug("need to create table buildfarm_postgresql")
            self.table_buildfarm_postgresql()



    # drop_tables()
    #
    # drop all existing tables
    #
    # parameter:
    #  - self
    # return:
    #  none
    def drop_tables(self):
        if (self.table_exist('build_status') is True):
            logging.debug("drop table build_status")
            self.drop_table('build_status')

        if (self.table_exist('buildfarm_jobs') is True):
            logging.debug("drop table buildfarm_jobs")
            self.drop_table('buildfarm_jobs')

        if (self.table_exist('buildfarm_postgresql') is True):
            logging.debug("drop table buildfarm_postgresql")
            self.drop_table('buildfarm_postgresql')



    # drop_table()
    #
    # drop a specific table
    #
    # parameter:
    #  - self
    #  - table name
    # return:
    #  none
    def drop_table(self, table):
        # there is no sane way to quote identifiers in Python for SQLite
        # assume that the table name is safe, and that the author of this module
        # never uses funny table names
        query = 'DROP TABLE "%s"' % table
        self.execute_one(query, [])



    # run_query()
    #
    # execute a database query without parameters
    #
    # parameter:
    #  - self
    #  - query
    # return:
    #  none
    def run_query(self, query):
        cur = self.connection.cursor()
        cur.execute(query)
        self.connection.commit()



    # execute_one()
    #
    # execute a database query with parameters, return single result
    #
    # parameter:
    #  - self
    #  - query
    #  - list with parameters
    # return:
    #  - result
    def execute_one(self, query, param):
        cur = self.connection.cursor()

        cur.execute(query, param)
        result = cur.fetchone()

        self.connection.commit()
        return result



    # execute_query()
    #
    # execute a database query with parameters, return result set
    #
    # parameter:
    #  - self
    #  - query
    #  - list with parameters
    # return:
    #  - result set
    def execute_query(self, query, param):
        cur = self.connection.cursor()

        cur.execute(query, param)
        result = cur.fetchall()

        self.connection.commit()
        return result



    # fetch_all_from_build_status()
    #
    # fetch a list of build status log entries
    #
    # parameter:
    #  - self
    # return:
    #  - list with log entries (table: build_status)
    def fetch_all_from_build_status(self):
        query = """SELECT id , repository, repository_type, branch, revision, is_head, is_buildfarm, orca,
                          start_time, start_time_local,
                          run_git_update, run_configure, run_make, run_install, run_tests, extra_patches,
                          result_git_update, result_configure, result_make, result_install, result_tests, result_portcheck,
                          run_extra_targets, test_locales
                     FROM build_status
                 ORDER BY id"""
        return self.execute_query(query, [])



    # fetch_specific_build_status()
    #
    # fetch a specific build status log entry
    #
    # parameter:
    #  - self
    #  - id
    # return:
    #  - data for specific log entry
    def fetch_specific_build_status(self, id):
        query = """SELECT id, repository, repository_type, branch, revision, is_head, is_buildfarm, orca,
                          start_time, start_time_local,
                          run_git_update, run_configure, run_make, run_install, run_tests, extra_patches,
                          result_git_update, result_configure, result_make, result_install, result_tests, result_portcheck,
                          time_git_update, time_configure, time_make, time_install, time_tests, times_buildfarm,
                          extra_configure, extra_make, extra_install, extra_tests, patches, errorstr,
                          run_extra_targets, test_locales,
                          pg_majorversion, pg_version, pg_version_num, pg_version_str,
                          gp_majorversion, gp_version, gp_version_num, steps_buildfarm
                     FROM build_status
                    WHERE id = ?"""
        return self.execute_one(query, [id])



    # fetch_last_build_status_id()
    #
    # fetch the last build status log id (only non-buildfarm builds - interactive)
    #
    # parameter:
    #  - self
    # return:
    #  - id for last log entry
    def fetch_last_build_status_id(self):
        query = """SELECT COALESCE(MAX(id), 'not set') AS id
                     FROM build_status
                    WHERE is_buildfarm = 0"""
        return self.execute_one(query, [])



    # buildfarm_ran_before()
    #
    # verify if a specific buildfarm job ran before
    # FIXME: locales
    # FIXME: extra targets
    #
    # parameter:
    #  - self
    #  - repository name
    #  - branch name
    #  - revision string
    # return:
    #  - True/False
    def buildfarm_ran_before(self, repository, branch, revision):
        query = """SELECT COUNT(*) AS count
                     FROM build_status
                    WHERE is_buildfarm = 1
                      AND repository = ?
                      AND branch = ?
                      AND revision = ?"""
        result = self.execute_one(query, [repository, branch, revision])
        if (result['count'] > 0):
            return True
        else:
            return False



    # last_log_entry()
    #
    # return the last log entry for a specific combination of repository, branch and revision
    # FIXME: locales
    # FIXME: extra targets
    #
    # parameter:
    #  - self
    #  - repository name
    #  - branch name
    #  - revision string
    #  - optional: is buildfarm (default: False)
    # return:
    #  - False, or build status log entry
    def last_log_entry(self, repository, branch, revision, is_buildfarm = False, start_time = None):
        if (is_buildfarm is True):
            is_buildfarm = 1
        else:
            is_buildfarm = 0

        if (start_time is None):
            query = """SELECT id
                         FROM build_status
                        WHERE is_buildfarm = ?
                          AND repository = ?
                          AND branch = ?
                          AND revision = ?
                     ORDER BY start_time DESC, id DESC
                        LIMIT 1"""
            param = [is_buildfarm, repository, branch, revision]
        else:
            query = """SELECT id
                         FROM build_status
                        WHERE is_buildfarm = ?
                          AND repository = ?
                          AND branch = ?
                          AND revision = ?
                          AND start_time = ?
                     ORDER BY start_time DESC, id DESC
                        LIMIT 1"""
            param = [is_buildfarm, repository, branch, revision, start_time]
        result = self.execute_one(query, param)
        # no result
        if (result is None):
            return False
        return self.fetch_specific_build_status(result['id'])



    # previous_log_entry()
    #
    # return the previous last log entry for a specific combination of repository, branch and revision
    # FIXME: locales
    # FIXME: extra targets
    #
    # parameter:
    #  - self
    #  - last ID
    #  - repository name
    #  - branch name
    #  - revision string
    #  - optional: is buildfarm (default: False)
    #  - optional: without error (default: False)
    # return:
    #  - False, or build status log entry
    def previous_log_entry(self, this_id, repository, branch, revision, is_buildfarm = False, without_error = False):
        if (is_buildfarm is True):
            is_buildfarm = 1
        else:
            is_buildfarm = 0

        # this is scanning the log table for the first entry (timewise) which does
        # not match the current revision and is older than the current revision
        if (without_error is False):
            query = """SELECT id
                         FROM build_status
                        WHERE is_buildfarm = ?
                          AND repository = ?
                          AND branch = ?
                          AND revision != ?
                          AND id < ?
                     ORDER BY start_time DESC, id DESC
                        LIMIT 1"""
        else:
            query = """SELECT id
                         FROM build_status
                        WHERE is_buildfarm = ?
                          AND repository = ?
                          AND branch = ?
                          AND revision != ?
                          AND id < ?
                          AND result_configure = 0
                          AND result_make = 0
                          AND result_install = 0
                          AND result_tests = 0
                     ORDER BY start_time DESC, id DESC
                        LIMIT 1"""
        result = self.execute_one(query, [is_buildfarm, repository, branch, revision, this_id])
        # no result
        if (result is None):
            return False
        return self.fetch_specific_build_status(result['id'])



    # buildfarm_job_exists()
    #
    # verify if a specific buildfarm job exists in the queue or history
    #
    # parameter:
    #  - self
    #  - repository name
    #  - branch name
    #  - revision string
    #  - extra configure string
    #  - extra make string
    #  - extra install string
    #  - extra tests string
    #  - optional: Orca enabled (default: exclude)
    #  - optional: job already finished (default: exclude)
    # return:
    #  - True/False
    def buildfarm_job_exists(self, repository, branch, revision, extra_configure, extra_make, extra_install, extra_tests, run_extra_targets, test_locales, orca = None, finished = None):
        query = """SELECT COUNT(*) AS count
                     FROM buildfarm_jobs
                    WHERE repository = ?
                      AND branch = ?
                      AND revision = ?
                      AND extra_configure = ?
                      AND extra_make = ?
                      AND extra_install = ?
                      AND extra_tests = ?
                      AND run_extra_targets = ?
                      AND test_locales = ?"""
        params = [repository, branch, revision, extra_configure, extra_make, extra_install, extra_tests, run_extra_targets, test_locales]
        if (orca is True):
            query += " AND orca = ?"
            params.append("1")
        if (orca is False):
            query += " AND orca = ?"
            params.append("0")

        if (finished is True):
            query += " AND finished = ?"
            params.append("1")
        if (finished is False):
            query += " AND finished = ?"
            params.append("0")

        result = self.execute_one(query, params)
        if (result['count'] > 0):
            return True
        else:
            return False



    # add_bildfarm_job()
    #
    # add a new buildfarm job
    #
    # parameter:
    #  - self
    #  - buildfarm job data object
    # return:
    #  none
    def add_bildfarm_job(self, job_in):
        # create a copy, because we modify the content
        job = copy.deepcopy(job_in)
        if (job['is_head'] is True):
            job['is_head'] = 1
        else:
            job['is_head'] = 0

        if (job['orca'] is True):
            job['orca'] = 1
        else:
            job['orca'] = 0

        query = """INSERT INTO buildfarm_jobs
                               (finished, added_ts, executed_ts, repository, branch, revision, is_head,
                                orca, extra_configure, extra_make, extra_install, extra_tests,
                                run_extra_targets, test_locales)
                        VALUES (0, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

        param = [job['added_ts'], job['repository'], job['branch'], job['revision'], job['is_head'],
                 job['orca'], job['extra-configure'], job['extra-make'], job['extra-install'], job['extra-tests'],
                 job['run-extra-targets'], job['test-locales']]

        self.execute_one(query, param)



    # list_pending_buildfarm_jobs()
    #
    # list all pending buildfarm jobs (queue entries)
    #
    # parameter:
    #  - self
    # return:
    #  - list with open objects
    def list_pending_buildfarm_jobs(self):
        # search only jobs which are at least 1 hour old (initial time is 0)
        find_time = int(time.time()) - 3600
        query = """SELECT id, finished, added_ts, executed_ts, repository, branch, revision, is_head,
                          orca, extra_configure, extra_make, extra_install, extra_tests,
                          run_extra_targets, test_locales
                     FROM buildfarm_jobs
                    WHERE finished = 0
                      AND executed_ts < ?
                 ORDER BY added_ts ASC"""

        return self.execute_query(query, [find_time])



    # fetch_specific_buildfarm_job()
    #
    # fetch a specific buildfarm queue entry
    #
    # parameter:
    #  - self
    #  - id
    # return:
    #  - data for specific buildfarm queue entry
    def fetch_specific_buildfarm_job(self, id):
        query = """SELECT id, finished, added_ts, executed_ts, repository, branch, revision, is_head,
                          orca, extra_configure, extra_make, extra_install, extra_tests,
                          run_extra_targets, test_locales
                     FROM buildfarm_jobs
                    WHERE id = ?"""

        return self.execute_one(query, [id])



    # list_all_buildfarm_jobs()
    #
    # list all buildfarm jobs (pending and finished)
    #
    # parameter:
    #  - self
    # return:
    #  - list with all objects
    def list_all_buildfarm_jobs(self):
        query = """SELECT id, finished, added_ts, executed_ts, repository, branch, revision, is_head,
                          orca, extra_configure, extra_make, extra_install, extra_tests,
                          run_extra_targets, test_locales
                     FROM buildfarm_jobs
                 ORDER BY added_ts ASC"""

        return self.execute_query(query, [])



    # update_buildfarm_job_finished()
    #
    # mark a buildfarm job as finished
    #
    # parameter:
    #  - self
    #  - job id
    #  - timestamp when job was executed
    # return:
    #  none
    def update_buildfarm_job_finished(self, id, executed_ts):
        query = "UPDATE buildfarm_jobs SET finished = 1, executed_ts = ? WHERE id = ?"

        self.execute_one(query, [executed_ts, id])

        logging.debug("mark job as finished: " + str(id))



    # update_buildfarm_job_delayed()
    #
    # mark a buildfarm job as delayed
    #
    # parameter:
    #  - self
    #  - job id
    #  - timestamp when job was executed
    # return:
    #  none
    def update_buildfarm_job_delayed(self, id, executed_ts):
        query = "UPDATE buildfarm_jobs SET executed_ts = ? WHERE id = ?"

        self.execute_one(query, [executed_ts, id])

        logging.debug("mark job as delayed: " + str(id))



    # update_buildfarm_job_requeued()
    #
    # requeue a buildfarm job
    #
    # parameter:
    #  - self
    #  - job id
    # return:
    #  none
    def update_buildfarm_job_requeued(self, id):
        query = "UPDATE buildfarm_jobs SET executed_ts = 0, finished = 0 WHERE id = ?"

        self.execute_one(query, [id])

        logging.debug("mark job as requeued: " + str(id))



    # table_exist()
    #
    # verify if a table exists in the database
    #
    # parameter:
    #  - self
    #  - table name
    # return:
    #  - True/False
    def table_exist(self, table):
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = self.execute_one(query, [table])
        if (result is None):
            return False
        else:
            return True



    # table_build_status()
    #
    # create the 'build_status' table
    #
    # parameter:
    #  - self
    # return:
    #  none
    def table_build_status(self):
        query = """CREATE TABLE build_status (
                id INTEGER PRIMARY KEY NOT NULL,
                repository TEXT NOT NULL,
                repository_type TEXT DEFAULT '',
                branch TEXT DEFAULT '',
                revision TEXT DEFAULT '',
                is_head BOOLEAN,
                is_buildfarm BOOLEAN NOT NULL,
                orca BOOLEAN,
                start_time INTEGER NOT NULL,
                start_time_local TEXT NOT NULL,
                run_git_update BOOLEAN NOT NULL,
                run_configure BOOLEAN NOT NULL,
                run_make BOOLEAN NOT NULL,
                run_install BOOLEAN NOT NULL,
                run_tests BOOLEAN NOT NULL,
                run_extra_targets TEXT NOT NULL DEFAULT '',
                time_git_update REAL NOT NULL,
                time_configure REAL NOT NULL,
                time_make REAL NOT NULL,
                time_install REAL NOT NULL,
                time_tests REAL NOT NULL,
                times_buildfarm TEXT NOT NULL DEFAULT '',
                steps_buildfarm TEXT NOT NULL DEFAULT '',
                result_portcheck INTEGER,
                result_git_update INTEGER,
                result_configure INTEGER,
                result_make INTEGER,
                result_install INTEGER,
                result_tests INTEGER,
                extra_configure TEXT NOT NULL DEFAULT '',
                extra_make TEXT NOT NULL DEFAULT '',
                extra_install TEXT NOT NULL DEFAULT '',
                extra_tests TEXT NOT NULL DEFAULT '',
                extra_patches BOOLEAN NOT NULL,
                test_locales TEXT NOT NULL DEFAULT '',
                patches TEXT NOT NULL DEFAULT '',
                errorstr TEXT NOT NULL DEFAULT '',
                pg_majorversion TEXT,
                pg_version TEXT,
                pg_version_num TEXT,
                pg_version_str TEXT,
                gp_majorversion TEXT,
                gp_version TEXT,
                gp_version_num TEXT
                )"""
        self.run_query(query)



    # table_buildfarm_jobs()
    #
    # create the 'buildfarm_jobs' table
    #
    # parameter:
    #  - self
    # return:
    #  none
    def table_buildfarm_jobs(self):
        query = """CREATE TABLE buildfarm_jobs (
                id INTEGER PRIMARY KEY NOT NULL,
                finished BOOLEAN NOT NULL,
                added_ts INTEGER NOT NULL,
                executed_ts INTEGER NOT NULL,
                repository TEXT NOT NULL,
                branch TEXT NOT NULL,
                revision TEXT NOT NULL,
                is_head BOOLEAN NOT NULL,
                orca BOOLEAN NOT NULL DEFAULT FALSE,
                extra_configure TEXT NOT NULL DEFAULT '',
                extra_make TEXT NOT NULL DEFAULT '',
                extra_install TEXT NOT NULL DEFAULT '',
                extra_tests TEXT NOT NULL DEFAULT '',
                run_extra_targets TEXT NOT NULL DEFAULT '',
                test_locales TEXT NOT NULL DEFAULT ''
                )"""
        self.run_query(query)



    # table_buildfarm_postgresql()
    #
    # create the 'buildfarm_postgresql' table
    #
    # parameter:
    #  - self
    # return:
    #  none
    def table_buildfarm_postgresql(self):
        query = """CREATE TABLE buildfarm_postgresql (
                id INTEGER PRIMARY KEY NOT NULL,
                sent BOOLEAN NOT NULL,
                last_tried_ts INTEGER NOT NULL,
                success_ts INTEGER NOT NULL,
                tries INTEGER NOT NULL
                )"""
        self.run_query(query)

