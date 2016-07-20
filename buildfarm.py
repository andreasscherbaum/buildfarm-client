import re
import os
import sys
import logging
import shlex
import glob
import subprocess
from subprocess import Popen, PIPE


class Buildfarm:

    def __init__(self, config, repository, build_dir, database):
        self.config = config
        self.repository = repository
        self.build_dir = build_dir
        self.database = database


    def send_results(self, log_data):
        self.create_directory_in_home_if_not_exists(".buildclient-buildfarm.tmp")
        # decide which buildfarm is supposed to handle the send_results
        if (log_data['repository_type'] == 'PostgreSQL'):
            self.send_results_postgresql(log_data)
        elif (log_data['repository_type'] == 'Greenplum'):
            self.send_results_greenplum(log_data)
        else:
            logging.error("Unknown repository type: " + log_data['repository_type'])
            sys.exit(1)


    def send_results_postgresql(self, log_data):
        self.create_directory_in_home_if_not_exists(os.path.join(".buildclient-buildfarm.tmp", "PostgreSQL"))

        # findings
        # - changed_files: list of changed files since last run, plus space, plus last git revision
        #   the list is joined by '!'
        #   the field is '' if there are no files
        #
        # - changed_since_success: like 'changed_files', but goes back all the way to the previous
        #   successful build
        #   the list is joined by '!'
        #   this field is only populated if there is an error, and a previous build
        #
        # - branch: name of the branch
        #
        # - res: result FIXME: verify
        #
        # - stage: the stage name where something failed, or 'OK' if everything is successful
        #
        # - animal: the buildfarm username
        #
        # - ts: unix timestamp where the whole operation started
        #   runtimes are calculated based on this timestamp
        #   'ts' can only be 120 seconds in the future, or 86400 seconds in the past
        #     other values are rejected by the PostgreSQL buildfarm
        #
        # - log: log entry
        #
        # - conf: configuration FIXME: verify
        #
        # - frozen_sconf: configuration FIXME: verify
        #
        # - logtar: tar/gz archive with logfiles
        #   the runtime for every stage is calculated based on the stat[9] (mtime)
        #     difference between 'ts'
        #   the file 'githead.log' is not included in server output
        #     however the file contains the git revision which is extracted
        #
        # - the following fields are base64 encoded, and "proofed":
        #   - log_data: FIXME: ???
        #   - confsum: FIXME: ???
        #   - changed_files
        #   - changed_since_success
        #   - logtar
        #   - frozen_sconf
        #
        # - algorithm used for base64 encoding and "proofing":
        #     perl -e 'use MIME::Base64; $a = "Test"; map{ $_=encode_base64($_,""); tr/+=/$@/; }($a); print "a: $a\n";'
        #       a: VGVzdA@@
        #   without the "proofing":
        #     perl -e 'use MIME::Base64; $a = "Test"; map{ $_=encode_base64($_,""); }($a); print "a: $a\n";'
        #       a: VGVzdA==
        #   note: the server does not verify if the data is "proofed"
        #
        # - sig: the additional URL path, after pgstatus.pl, minus leading slash
        #     my $query = new CGI;
        #     my $sig = $query->path_info;
        #     $sig =~ s!^/!!;
        #   http://perldoc.perl.org/CGI.html
        #   POST /cgi-bin/pgstatus.pl/20f16c47718d6da0460eb69930edfd5edd9e6d9a HTTP/1.1
        #
        #     my $content = "branch=$branch&res=$res&stage=$stage&animal=$animal&ts=$ts&log=$log&conf=$conf";
        #     my $extra_content = "changed_files=$changed_this_run&changed_since_success=$changed_since_success&";
        #
        #     my $calc_sig = sha1_hex($content, $secret);
        #     my $calc_sig2 = sha1_hex($extra_content, $content, $secret);
        #
        #     if ($calc_sig ne $sig && $calc_sig2 ne $sig)
        #
        #
        # - hostname for requests is: Host: www.pgbuildfarm.org
        #
        # - username for requests is: Postgres Build Farm Reporter
        #
        #
        # The following fields are included in the POST request:
        #
        #changed_files=
        #changed_since_success=
        #branch=HEAD
        #res=0
        #stage=OK
        #animal=croaker
        #ts=1459882463
        #log=TGFzdCBmaWxlIG10aW1lIGluIHNuYXBzaG90OiBUdWUgQXByICA1IDE4OjUxOjE5IDIwMTYgR01UCj09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQo@
        #conf=
        #frozen_sconf=
        #logtar=
        #
        #
        # - error codes:
        #
        # * Status: 492 bad branch parameter
        #   - list of expected branches in: https://github.com/PGBuildFarm/server-code/blob/master/htdocs/branches_of_interest.txt
        #     HEAD = master/HEAD
        #
        # * Status: 490 bad parameters
        #   - expected parameters:
        #     * $animal, $ts, $stage, $sig
        #
        # * Status: 495 Unknown System
        #   - if the animal is not in the 'buildsystems' table (column: name) and status = 'approved'
        #
        # * Status: 450 sig mismatch
        #   - Signature 1 or 2 do not match
        #
        # * Status: 491 bad ts parameter ...
        #   - timestamp is out of range
        #
        # * Status: 493 snapshot too old: ...
        #   - the current revision is too old
        #   - currently not verified
        #
        # * Status: 460 script version too low
        #   - client side script is outdated
        #     'script_version' => 'REL_4.17'
        #
        # * Status: 461 web script version too low
        #   - client side script is outdated
        #     'web_script_version' => 'REL_4.17'
        #
        # * Status: 462 database failure
        #   - internal server problem
        #
        # * Status: 200 OK
        #   - generated by DBI
        #     print "request was on:\n";
        #     print "res=$res&stage=$stage&animal=$animal&ts=$ts";
        #
        #
        # the following files are in logtar, in reverse --sort=time order (first files listed first)
        #
        # SCM-checkout.log                      not included in this buildfarm: checkout happens earlier
        # githead.log                           includes only the revision, written in Build.run_configure()
        # configure.log                         ./configure output, written in Build.run_configure()
        # config.log                            ./configure results, written in Build.run_configure()
        # make.log                              "make" output, written in Build.run_make()
        # check.log                             mingle-mangle of "make check" and other files, written in Build.run_tests()
        # make-contrib.log                      output of "make" in contrib/, written in Build.run_tests()
        # make-testmodules.log
        # make-install.log
        # install-contrib.log
        # install-testmodules.log
        # check-pg_upgrade.log                  output of "make check" in src/bin/pg_upgrade or contrib/pg_upgrade, written in Build.run_tests()
        # test-decoding-check.log
        # initdb-C.log
        # startdb-C-1.log
        # install-check-C.log
        # stopdb-C-1.log
        # startdb-C-2.log
        # isolation-check.log
        # stopdb-C-2.log
        # startdb-C-3.log
        # pl-install-check-C.log
        # stopdb-C-3.log
        # startdb-C-4.log
        # contrib-install-check-C.log
        # stopdb-C-4.log
        # startdb-C-5.log
        # testmodules-install-check-C.log
        # stopdb-C-5.log
        # ecpg-check.log
        #
        #
        # missing: "bin-check.log" - only in 9.4 and later, and only with --enable-tap-tests
        #
        #
        #
        #Stages:
        # OK, distclean, Make, Doc, Install, Contrib, TestModules, ContribInstall, TestModulesInstall
        # Initdb-$locale, StartDb-$locale:$started_times, StopDb-$locale:$started_times
        # InstallCheck-$locale, ContribCheck-$locale, TestModulesCheck-$locale, PLCheck-$locale
        # IsolationCheck, BinInstallCheck, Check, ECPG-Check, Configure
        # test-decoding-check
        # $MODULE-build, $MODULE-install, $MODULE-installcheck-$locale
        # sepgsql-policy-build, sepgsql-policy-install, test-sepgsql
        # InstallCheck-collate-$locale
        # pg_upgradeCheck
        # $target-CVS, $target-CVS-Merge, $target-CVS-Dirty, $target-CVS-Extraneous-Files
        # $target-CVS-Extraneous-Ignore, $target-CVS-status, Git-mirror, $target-Git, $target-Git-Dirty
        #
        #
        # 'steps_completed' => 'SCM-checkout Configure Make Check Contrib TestModules Install ContribInstall TestModulesInstall pg_upgradeCheck test-decoding-check Initdb-C InstallCheck-C IsolationCheck PLCheck-C ContribCheck-C TestModulesCheck-C ECPG-Check',








        # honor 'send_results' flag
        if (self.config.get('send-results') is False):
            logging.info("Not sending results to buildfarm server")
            return True
        logging.debug("Sending results to buildfarm server ...")





        # there should be an entry, because it was written moments ago
        result_this = self.database.last_log_entry(log_data['repository'], log_data['branch'], log_data['revision'], is_buildfarm = True, start_time = log_data['start_time'])
        if (result_this is False):
            logging.error("Can't find current log entry in database")
            sys.exit(1)
        #print("    this result: " + str(result_this))


        result_previous = self.database.previous_log_entry(result_this['id'], log_data['repository'], log_data['branch'], log_data['revision'], is_buildfarm = True)
        if (result_previous is False):
            logging.debug("no previous log entry in database")
            changed_files = ''
        else:
            #print("previous result: " + str(result_previous))
            changed_files = self.repository.changed_files_with_commits(result_previous['revision'], result_this['revision'])

        #print("changes:" + os.linesep + changed_files)


        result_previous_success = self.database.previous_log_entry(result_this['id'], log_data['repository'], log_data['branch'], log_data['revision'], is_buildfarm = True, without_error = True)
        if (result_previous_success is False):
            logging.debug("no previous log entry for a successful run in database")
            changed_since_success = ''
        else:
            #print("previous result: " + str(result_previous_success))
            changed_since_success = self.repository.changed_files_with_commits(result_previous_success['revision'], result_this['revision'])


        res = 0
        stage = ''
        steps_completed = []

        # see if and where it failed
        if (result_this['run_git_update'] == 1 and result_this['result_git_update'] > 0):
            res = result_this['result_git_update']
            stage = 'SCM'
        elif (result_this['result_portcheck'] is not None and result_this['result_portcheck'] > 0):
            res = result_this['result_portcheck']
            stage = 'Pre-run-port-check'
        elif (result_this['run_configure'] == 1 and result_this['result_configure'] > 0):
            res = result_this['result_configure']
            stage = 'Configure'
        elif (result_this['run_make'] == 1 and result_this['result_make'] > 0):
            res = result_this['result_make']
            stage = 'Make'
        elif (result_this['run_install'] == 1 and result_this['result_install'] > 0):
            res = result_this['result_install']
            stage = 'Make-install'
        elif (result_this['run_tests'] == 1 and result_this['result_tests'] > 0):
            res = result_this['result_tests']
            stage = 'Check'
        else:
            res = 0
            stage = 'OK'

        if (result_this['run_git_update'] == 1):
            steps_completed.append("SCM-checkout")
        if (result_this['run_configure'] == 1):
            steps_completed.append("Configure")
        if (result_this['run_make'] == 1):
            steps_completed.append("Make")
        if (result_this['run_install'] == 1):
            steps_completed.append("Install")
        if (result_this['run_tests'] == 1):
            steps_completed.append("Check")

        buildlogs = os.path.join(self.build_dir, '.buildfarm-logs')
        if (os.path.isfile(os.path.join(buildlogs, 'make-contrib.log'))):
            steps_completed.append("Contrib")
        if (os.path.isfile(os.path.join(buildlogs, 'make-testmodules.log'))):
            steps_completed.append("TestModules")
        if (os.path.isfile(os.path.join(buildlogs, 'install-contrib.log'))):
            steps_completed.append("ContribInstall")
        if (os.path.isfile(os.path.join(buildlogs, 'install-testmodules.log'))):
            steps_completed.append("TestModulesInstall")
        if (os.path.isfile(os.path.join(buildlogs, 'check-pg_upgrade.log'))):
            steps_completed.append("pg_upgradeCheck")
        if (os.path.isfile(os.path.join(buildlogs, 'test-decoding-check.log'))):
            steps_completed.append("test-decoding-check")
        if (os.path.isfile(os.path.join(buildlogs, 'ecpg-check.log'))):
            steps_completed.append("ECPG-Check")


        # find all 'initdb-*.log' logfiles, extract the locale
        initdb_list = glob.glob(buildlogs + os.sep + 'initdb-*.log')
        for initdb in initdb_list:
            initdb_file = os.path.basename(initdb)
            initdb_locale = initdb_file[7:][:-4]
            steps_completed.append("Initdb-" + initdb_locale)
            if (os.path.isfile(os.path.join(buildlogs, 'install-check-' + initdb_locale + '.log'))):
                steps_completed.append("InstallCheck-" + initdb_locale)
            if (os.path.isfile(os.path.join(buildlogs, 'isolation-check-' + initdb_locale + '.log'))):
                steps_completed.append("IsolationCheck-" + initdb_locale)
            if (os.path.isfile(os.path.join(buildlogs, 'pl-install-check-' + initdb_locale + '.log'))):
                steps_completed.append("PLCheck-" + initdb_locale)
            if (os.path.isfile(os.path.join(buildlogs, 'contrib-install-check-' + initdb_locale + '.log'))):
                steps_completed.append("ContribCheck-" + initdb_locale)
            if (os.path.isfile(os.path.join(buildlogs, 'testmodules-install-check-' + initdb_locale + '.log'))):
                steps_completed.append("TestModulesCheck-" + initdb_locale)
        steps_completed = " ".join(steps_completed)
        # 'steps_completed' => 'ContribCheck-C TestModulesCheck-C',
        print("steps completed: " + steps_completed)



        branch = log_data['branch']
        if (branch is None):
            branch = '?'

        animal = self.config.get('buildfarm-animal')
        secret = self.config.get('buildfarm-secret')

        ts = log_data['start_time']

        log = ''


        # build a minimal config
        conf = "$Script_Config =" + os.linesep
        conf += "{" + os.linesep
        conf += " 'animal' => '" + animal + "'," + os.linesep
        conf += " 'script_version' => 'REL_4.17'," + os.linesep
        conf += " 'web_script_version' => 'REL_4.17'," + os.linesep
        conf += " 'current_ts' => " + str(ts) + "," + os.linesep
        conf += " 'build_root' => '" + self.config.get('build-dir') + "'," + os.linesep
        conf += " 'git_keep_mirror' => 1," + os.linesep
        conf += " 'target' => 'http://www.pgbuildfarm.org/cgi-bin/pgstatus.pl'," + os.linesep
        conf += " 'upgrade_target' => 'http://www.pgbuildfarm.org/cgi-bin/upgrade.pl'," + os.linesep
        if (self.config.get('clean-on-failure') is True):
            conf += " 'keep_error_builds' => 0," + os.linesep
        else:
            conf += " 'keep_error_builds' => 1," + os.linesep
        conf += " 'orig_env' => {" + os.linesep

        env_blacklist = ['PGPASSWORD']
        env_whitelist = ['MAKE', 'CC', 'CPP', 'CXX', 'FLAG', 'LIBRAR', 'INCLUDE']
        env_whitelist.extend(['HOME', 'LOGNAME', 'USER', 'PATH', 'SHELL', 'LD', 'LD_LIBRARY_PATH'])
        env = []
        for k in os.environ.keys():
            v = os.environ[k]
            if (k in env_blacklist):
                v = 'xxxxxx'
            elif (k in env_whitelist):
                pass
            else:
                v = 'xxxxxx'
            env.append("'" + k + "' => '" + v + "'")
        conf += "    " + ",\n    ".join(env) + os.linesep
        conf += " }," + os.linesep

        conf += " 'extra_config' => { }," + os.linesep
        conf += " 'locales' => [ ]," + os.linesep
        conf += " 'steps_completed' => [ " + steps_completed + " ]" + os.linesep
        if (len(self.config.get('extra-configure')) > 0):
            config_opts = []
            tmp1 = shlex.split(self.config.get('extra-configure'))
            for tmp2 in tmp1:
                config_opts.append("'" + tmp2 + "'")
            config_opts = ",\n".join(config_opts)
        else:
            config_opts = ''
        # last line without ',' at the end
        conf += " 'config_opts' => [ " + config_opts + " ]" + os.linesep
        conf += "};" + os.linesep
        #print("conf:" + os.linesep + conf)


        # gather logfiles for buildfarm server
        logfiles = list(filter(os.path.isfile, glob.glob(buildlogs + os.sep + "*.log")))
        logfiles.sort(key = lambda f: os.path.getmtime(f))
        logfiles = [os.path.basename(x) for x in logfiles]
        #print("logfiles: " + str(logfiles))
        logging.debug(str(len(logfiles)) + " logfiles for buildfarm server")
        # quickly change directory, create the tarball, and come back
        tar = self.config.get('tar-bin') + " -z -cf runlogs.tgz " + " ".join(logfiles)
        call = shlex.split(tar)
        proc = Popen(call, stdout=PIPE, stderr=subprocess.STDOUT, cwd=buildlogs)
        out, err = proc.communicate()
        exitcode = proc.returncode
        if (exitcode > 0):
            logging.error("unable to create tar archive for buildfarm server")
            logging.error("error: " + str(err))
            return False


#changed_files=
#changed_since_success=
#branch=HEAD
#res=0
#stage=OK
#animal=croaker
#ts=1459882463
#log=TGFzdCBmaWxlIG10aW1lIGluIHNuYXBzaG90OiBUdWUgQXByICA1IDE4OjUxOjE5IDIwMTYgR01UCj09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQo@
#conf=
#frozen_sconf=
#logtar=


        # proof server data:
        print("changed_files: " + str(len(changed_files)) + " bytes")
        print("changed_since_success: " + str(len(changed_since_success)) + " bytes")
        print("branch: " + str(branch))
        print("res: " + str(res))
        print("stage: " + str(stage))
        print("animal: " + str(animal))
        print("ts: " + str(ts))
        print("log: " + str(log))
        print("conf: " + str(len(conf)) + " bytes")





        return True




    def send_results_greenplum(self, log_data):
        logging.error("Buildfarm mode for Greenplum not yet implemented")
        sys.exit(1)
        self.create_directory_in_home_if_not_exists(os.path.join(".buildclient-buildfarm.tmp", "Greenplum"))

        # honor 'send_results' flag
        if (self.config.get('send-results') is False):
            logging.info("Not sending results to buildfarm server")
            return True
        logging.debug("Sending results to buildfarm server ...")



    def create_directory_in_home_if_not_exists(self, dir):
        # the config module ensures that $HOME is set
        path = os.path.join(os.environ.get('HOME'), dir)
        if (not os.path.exists(path)):
            try:
                os.mkdir(path, 0o0700)
            except OSError as e:
                logging.error("failed to create directory: " + dir)
                logging.error("Error: " + e.strerror)
                sys.exit(1)

