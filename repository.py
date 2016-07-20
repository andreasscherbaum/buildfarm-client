import re
import os
import sys
import shutil
import subprocess
import logging
import time
from subprocess import Popen, PIPE
import shlex
import atexit
import datetime
import sys
if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf8')

# this class must be initialized per repository/branch/revision


class Repository:

    def __init__(self, config, database, repository, cache_dir):
        self.config = config
        self.database = database
        self.repository = repository
        self.hashname = self.config.create_hashname(repository)
        self.cache_dir = cache_dir
        self.full_path = os.path.join(self.cache_dir, self.hashname)
        self.repository_type = False
        self.cleanup = []

        # verify that a repository is specified
        if (len(self.repository) == 0):
            logging.error("Error: No repository url specified")
            sys.exit(1)

        atexit.register(self.exit_handler)



    def exit_handler(self):
        if (self.config.get('clean-on-failure') == True and self.config.get('clean-everything') == True):
            for dir in self.cleanup:
                logging.debug("remove directory after error: " + dir)
                shutil.rmtree(dir, ignore_errors=True)



    # handle_update()
    #
    # handle update of repository plus verify that a local copy exists
    #
    # parameter:
    #  - self
    #  - run_update flag
    #  - log data object
    # return:
    #  none
    def handle_update(self, run_update, log_data):
        if (run_update is True):
            t_start = datetime.datetime.now()
            repo_update = self.update_repository(log_data)
            t_end = datetime.datetime.now()
            t_run = (t_end - t_start).total_seconds()
            log_data['time_git_update'] = t_run
            log_data['run_git_update'] = True
            if (repo_update is False):
                self.database.log_build(log_data)
                sys.exit(1)
        elif (self.repository_available_offline() is False):
            log_data['errstr'] = 'No local copy of repository'
            self.database.log_build(log_data)
            sys.exit(1)



    # repository_available_offline()
    #
    # verify that a local copy of the repository is available
    #
    # parameter:
    #  - self
    # return:
    #  - True/False
    def repository_available_offline(self):
        if (os.path.isdir(self.full_path)):
            return True
        else:
            return False



    # update_repository()
    #
    # update a repository, check out the repository if necessary
    #
    # parameter:
    #  - self
    #  - log data object
    # return:
    #  - True/False
    def update_repository(self, log_data):
        git_depth = str(self.config.get('git-depth'))
        if (git_depth != '0'):
            git_depth = '--depth ' + git_depth + ' '
        else:
            git_depth = ''

        if not (os.path.isdir(self.full_path)):
            logging.info("no local copy of: " + self.repository)
            logging.info("cloning into: " + self.full_path)
            #run = self.run_git("--version")
            args = "clone --no-hardlinks -q " + git_depth + self.repository + " '" + self.full_path + "'"
            run = self.run_git(args)
            log_data['result_git_update'] = run[0]
            if (run[0] > 0):
                errorstr = self.print_git_error(run, args)
                log_data['errorstr'] = errorstr
                return False

        txt_file = self.full_path + ".txt"
        if not (os.path.isfile(txt_file)):
            f = open(txt_file, 'w')
            f.write("Repository: " + self.repository + os.linesep)
            f.close()

        # run update for the repository
        args = "-C '" + self.full_path + "' pull " + git_depth + "-q --ff-only --rebase=true"
        run = self.run_git(args)
        log_data['result_git_update'] = run[0]
        if (run[0] > 0):
            errorstr = self.print_git_error(run, args)
            log_data['errorstr'] = errorstr
            return False
        f = open(txt_file, 'a')
        f.write("Update: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + os.linesep)
        f.close()

        return True



    # run_git()
    #
    # run an arbitrary git command
    #
    # parameter:
    #  - self
    #  - string with git arguments
    # return:
    #  - list with:
    #    - git exit code
    #    - content of STDOUT
    #    - content of STDERR
    def run_git(self, arguments):
        git = self.config.get('git-bin')

        if (arguments[:3] == 'git'):
            print("")
            print("Error: do not precedent the command with 'git'!")
            print("Argument: " + arguments)
            sys.exit(1)

        call = shlex.split(git + ' ' + arguments)
        #print("call: " + str(call))
        #return [1, '', '']

        logging.debug(str(call))
        start_time = time.time()
        proc = Popen(call, stdout=PIPE, stderr=subprocess.STDOUT)
        out, err = proc.communicate()
        exitcode = proc.returncode
        end_time = time.time()
        run_time = "%.2f" % (end_time - start_time)
        logging.debug("runtime: " + str(run_time) + "s")

        return [exitcode, out]



    # print_git_error()
    #
    # print out git error messages
    #
    # parameter:
    #  - self
    #  - list with result from run_git()
    #  - git arguments string
    # return:
    #  - error string
    def print_git_error(self, run, command):
        print("")
        print("git failed (return code: " + str(run[0]) + ")")
        errorstr = ""
        if (len(run[1]) > 1):
            print("stdout/stderr:")
            #print(run[1])
            print("------------------------------------------")
            print("\n".join(run[1].decode().splitlines()[-20:]))
            print("------------------------------------------")
            print("")
            errorstr = "\n".join(run[1].decode().splitlines()[-20:])
        print("failing command:")
        print("git " + command)

        return errorstr



    # copy_repository()
    #
    # clone a git repository into the build directory
    #
    # parameter:
    #  - self
    #  - directory name for the build
    #  - branch name for checkout
    #  - revision name in branch
    # return:
    #  - full path to build directory + new directory name
    def copy_repository(self, name, branch, revision):
        build_dir = os.path.join(self.config.get('build-dir'), name)
        logging.info("build dir: " + build_dir)

        if not (os.path.isdir(self.full_path)):
            print("")
            print("No cached version of repository available!")
            print("Hint: did you run without --run-update?")
            sys.exit(1)

        git_dir = os.path.join(build_dir, '.git')

        args = "clone --local --mirror -q '" + self.full_path + "' '" + git_dir +  "'"
        run = self.run_git(args)
        self.dump_logs(build_dir, run, "git " + args, self.config.logfile_name("git", second_number = 1, second_type = 'clone'))
        if (run[0] > 0):
            self.print_git_error(run, args)
            self.cleanup.append(build_dir)
            sys.exit(1)

        args = "-C '" + build_dir + "' config --bool core.bare false"
        run = self.run_git(args)
        self.dump_logs(build_dir, run, "git " + args, self.config.logfile_name("git", second_number = 2, second_type = 'clone'))
        if (run[0] > 0):
            self.print_git_error(run, args)
            self.cleanup.append(build_dir)
            sys.exit(1)

        args = "-C '" + build_dir + "' checkout 'origin/" + branch + "'"
        run = self.run_git(args)
        self.dump_logs(build_dir, run, "git " + args, self.config.logfile_name("git", second_number = 3, second_type = 'checkout'))
        if (run[0] > 0):
            self.print_git_error(run, args)
            self.cleanup.append(build_dir)
            sys.exit(1)

        if (revision != 'HEAD'):
            args = "-C '" + build_dir + "' reset --hard '" + revision + "'"
            run = self.run_git(args)
            self.dump_logs(build_dir, run, "git " + args, self.config.logfile_name("git", second_number = 4, second_type = 'reset'))
            if (run[0] > 0):
                self.print_git_error(run, args)
                self.cleanup.append(build_dir)
                sys.exit(1)

        head = self.repository_head(build_dir)

        # ignore 'repository-info.txt', 'buildclient-config.txt' and all 'log_*.txt' files
        f = open(os.path.join(build_dir, '.git', 'info', 'exclude'), 'a')
        f.write("" + os.linesep)
        f.write("# added by buildclient" + os.linesep)
        f.write("buildclient-config.txt" + os.linesep)
        f.write("repository-info.txt" + os.linesep)
        f.write("log_*_cmdline.txt" + os.linesep)
        f.write("log_*_exit_code.txt" + os.linesep)
        f.write("log_*_stdout_stderr.txt" + os.linesep)
        f.write(".buildfarm-logs" + os.linesep)
        f.close()

        self.repository_type = self.identify_repository_type(build_dir)
        logging.debug("Repository type: " + self.repository_type)
        self.dump_config(build_dir)
        self.dump_repository_info(build_dir, branch, revision, head)

        return build_dir



    # repository_head()
    #
    # identify the head of a repository (latest revision)
    #
    # paramater:
    #  - self
    #  - repository directory
    # return:
    #  - latest revision identifier
    def repository_head(self, dir, branch = False):
        if (branch is False):
            args = "-C '" + dir + "' rev-parse HEAD"
        else:
            args = "-C '" + dir + "' rev-parse --branch='" + branch + "' HEAD"
        run = self.run_git(args)
        if (run[0] > 0):
            self.print_git_error(run, args, False)
            sys.exit(1)
        lines = run[1].splitlines()
        # Python 3 uses bytes, decode into string
        lines2 = []
        for i in lines:
            lines2.append(i.decode())
        lines = lines2
        if (lines[0][:9] == '--branch='):
            head = str(run[1].splitlines()[1].decode())
        else:
            head = str(run[1].splitlines()[0].decode())

        return head



    # dump_logs()
    #
    # write debugging content to files
    #
    # parameter:
    #  - self
    #  - path of build directory
    #  - list returned by run_git()
    #  - list of arguments sent to run_git()
    #  - template for output filename
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



    # dump_config()
    #
    # write the current configuration to a file
    #
    # parameter:
    #  - self
    #  - path of build directory
    # return:
    #  none
    def dump_config(self, build_dir):
        f = open(os.path.join(build_dir, 'buildclient-config.txt'), 'w')
        for key in self.config.getall():
            if (key == 'buildfarm-animal' or key == 'buildfarm-secret'):
                continue
            f.write(key + ': ' + str(self.config.get(key)) + os.linesep)
        f.close()



    # dump_repository_info()
    #
    # write information about the repository into a text file
    #
    # parameter:
    #  - self
    #  - path of build directory
    #  - branch name
    #  - revision name
    #  - current head in repository
    # return:
    #  none
    def dump_repository_info(self, build_dir, branch, revision, head):
        f = open(os.path.join(build_dir, 'repository-info.txt'), 'w')
        f.write("Repository: " + self.repository + os.linesep)
        f.write("Branch: " + branch + os.linesep)
        if (revision == 'HEAD'):
            f.write("Revision: " + head + " (HEAD)" + os.linesep)
        else:
            f.write("Revision: " + head + os.linesep)
        f.write("Type: " + self.repository_type + os.linesep)
        f.close()



    # identify_repository_type()
    #
    # identify the repository type
    #
    # parameter:
    #  - self
    #  - path to build directory
    # return:
    #  - "PostgreSQL" or "Greenplum"
    def identify_repository_type(self, build_dir):
        # verify if it is a Greenplum repository
        files = ['README.PostgreSQL', 'GNUmakefile.in', 'getversion', 'putversion', 'README.debian', 'LICENSE', 'COPYRIGHT']
        missing_files = False
        for file in files:
            if not (os.path.isfile(os.path.join(build_dir, file))):
                missing_files = True
        if (missing_files is False):
            # seems to be a Greenplum repository
            #logging.debug("repository type: Greenplum")
            return 'Greenplum'

        # verify if it is an internal Greenplum repository
        files = ['README.postgresql', 'GNUmakefile.in', 'getversion', 'putversion', 'LICENSE', 'COPYRIGHT']
        missing_files = False
        for file in files:
            if not (os.path.isfile(os.path.join(build_dir, file))):
                missing_files = True
        if (missing_files is False):
            # seems to be a Greenplum repository
            #logging.debug("repository type: Greenplum")
            return 'Greenplum'

        # verify if it is a PostgreSQL repository
        files = ['README.git', 'GNUmakefile.in', 'HISTORY', 'COPYRIGHT']
        missing_files = False
        for file in files:
            if not (os.path.isfile(os.path.join(build_dir, file))):
                missing_files = True
        if (missing_files is False):
            # seems to be a PostgreSQL repository
            #logging.debug("repository type: PostgreSQL")
            return 'PostgreSQL'

        # not able to identify repository type
        print("")
        print("not able to identify repository type")
        print("directory: " + build_dir)
        sys.exit(1)



    def changed_files_list(self, from_rev, to_rev):
        # git diff --name-status
        if not (os.path.isdir(self.full_path)):
            logging.error("Repository is not available!")
            sys.exit(1)

        # run diff for the two revisions
        args = "-C '" + self.full_path + "' diff --name-status " + from_rev + " " + to_rev
        run = self.run_git(args)
        if (run[0] > 0):
            self.print_git_error(run, args)
            sys.exit(1)

        lines = run[1].splitlines()
        # Python 3 uses bytes, decode into string
        lines2 = []
        for i in lines:
            lines2.append(i.decode())
        lines = lines2
        return str("\n".join(lines))



    def changed_files_with_commits(self, from_rev, to_rev):
        if not (os.path.isdir(self.full_path)):
            logging.error("Repository is not available!")
            sys.exit(1)

        # run diff for the two revisions
        args = "-C '" + self.full_path + "' log --name-only " + from_rev + ".." + to_rev
        run = self.run_git(args)
        if (run[0] > 0):
            self.print_git_error(run, args)
            sys.exit(1)

        lines = run[1].splitlines()
        # Python 3 uses bytes, decode into string
        lines2 = []
        for i in lines:
            lines2.append(i.decode())
        lines = lines2

        lines2 = []
        for i in lines:
            if (re.match('^[\s\t]', i) or len(i) == 0):
                continue
            if (i[0:7] == 'Author:' or i[0:5] == 'Date:'):
                continue
            c = re.match('^commit ([0-9a-zA-Z]+)', i)
            if (c):
                # remember the last commit id
                last_commit = c.group(1)
                continue
            # what's left should be a file name
            lines2.append(i.rstrip() + ' ' + last_commit)

        lines = lines2
        return str("!".join(lines))


