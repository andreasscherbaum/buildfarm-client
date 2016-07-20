# PostgreSQL and Greenplum buildclient

The buildclient has two modi:

* *interactive*: build PostgreSQL or Greenplum, and test new patches
* *buildfarm*: build and test new commits, and submit results to the buildfarm


Note: buildfarm mode is not yet fully implemented. Use _--no-send-results_ to avoid sending results to the buildfarm server.



## Before you start:


### Required Python modules:

re, tempfile, atexit, shutil, time, subprocess, socket, sqlite3, time, argparse, yaml,
hashlib, string, urllib2|urllib3, StringIO|io, gzip, zlib, copy, datetime, glob, logging,
os, shlex, stat, sys, urlparse|urljoin




### Create directories:

* *cache dir* (the tool will store a clone of every git repository in this directory)
* *build dir* (the repository will be cloned into this directory, and the build happens here)
* *install dir* (the build will be installed in this directory)

You can set these directories in the config file in the "build / dirs" section. _$HOME_ will be replaced by your home directory, _$TOPDIR_ will be replaced by what you specify in "build / dirs / top-dir".


### Verify installation

There is a test tool which verifies if you have all required modules installed, and all directories created:

```
./test-installation-pg.py -c demo-config-pg.yaml
./test-installation-gpdb.py -c demo-config-gpdb.yaml
```



## Interactive use

The interactive mode is suited for developers. You can specify which repository (your own or the official) you want to build, which branch and revision, and optionally which additional patches (see further down in this document) you want to apply before the build. Combined with _ccache_, this results in fast turnaround times while providing a clean environment every time a test is run.


How to use the tool interactively:

```
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-all
```

A good start is to use one of the provided configfiles (_demo-config-pg.yaml_ for PostgreSQL, _demo-config-gpdb.yaml_ for Greenplum), and modify it. Commandline options will override configfile options.


### Run only certain steps

Instead of _--run-all_, you can specify the steps:

```
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-configure
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-configure --run-make
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-configure --run-make --run-install
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-configure --run-make --run-install --run-tests
```

The "make" step requires "configure", the "install" step requires "make" and so on.


### Specify additional commandline options

For each step, additional commandline options can be specified:


```
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-configure --extra-configure "..."
```

The available options are:

```
--extra-configure
--extra-make
--extra-install
--extra-tests
```



## Apply a patch (only in interactive mode)

How to apply a patch:

Patches can be applied using the --patch option. This option can be specified multiple times. Every patch can be specified in several ways:

* path to the patch (compressed or uncompressed)
* URL to a GitHub Pull Request (patch will be downloaded)
* URL to a message in the PostgreSQL archive (all patches in this message will be downloaded)
* URL to a patch in the PostgreSQL archive (patch will be downloaded)
* Message-ID of a message in the PostgreSQL archive (all patches in this message will be downloaded, must contain one '@' character)
* URL to a commit in the PostgreSQL git repository
* hashsum of a commit in the PostgreSQL git repository

The tool will figure out how to uncompress and apply every patch (patch levels 0, 1, and 2 are tried). All patches are applied in the order they are specified. Also a final patch will be generated once all patches are applied. Use the _-v_ option to see all the details.

Examples:

```
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-all --patch /tmp/patch.gz
./buildclient.py -v -c demo-config-gpdb.yaml --no-clean-at-all --run-all --patch 'https://github.com/greenplum-db/gpdb/pull/457'
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-all --patch 'http://www.postgresql.org/message-id/20150831225328.GM2912@alvherre.pgsql'
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-all --patch 'http://www.postgresql.org/message-id/attachment/41737/64bit_3.diff'
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-all --patch 'http://www.postgresql.org/message-id/56AFBEF5.102@wars-nicht.de'
./buildclient.py -v -c demo-config-pg.yaml --no-clean-at-all --run-all --patch '56AFBEF5.102@wars-nicht.de'
./buildclient.py -v -c demo-config-gpdb.yaml --no-clean-at-all --run-all --patch 'http://git.postgresql.org/gitweb/?p=postgresql.git;a=commitdiff;h=085423e3e326da1b52f41aa86126f2a064a7db25'
./buildclient.py -v -c demo-config-gpdb.yaml --no-clean-at-all --run-all --patch 085423e3e326da1b52f41aa86126f2a064a7db25
```



## If something does not work

If everything runs smoothly, the resulting directories are deleted afterwards. This can be overridden by specifying _--no-clean-at-all_. In case of an error, the directories can be preserved using the option _--no-clean-on-failure_ option.


## List and show results

The buildclient stores results about each run in a SQLite3 database in the _~/.buildclient_ file.


### List all results (compact mode)

```
./buildclient.py -c demo-config-pg.yaml --list-results
```

This will show a list of all previous builds, along with an overview of which options were used, and if there was an error.


### Show a specific result

```
./buildclient.py -c demo-config-pg.yaml --show-result <number>
```



## Buildfarm mode

Add new jobs:

```
./buildclient.py -v -c demo-config-pg.yaml --buildfarm --run-all --add-jobs-only
```

Run buildfarm mode:

```
./buildclient.py -v -c demo-config-buildfarm.yaml --buildfarm --run-all
```

Both commands can run as a cronjob. The difference is that the first command only adds new jobs to the queue, and then releases the lockfile. This mode can only add jobs from PostgreSQL or Greenplum, not both in parallel. If "_HEAD_" is used as revision, the client will figure out the current head of the branch, and if new commits arrived. Then it will add new commit to the queue. The second command uses a different lockfile, and will build all jobs in the queue, no matter if PostgreSQL or Greenplum.

Failed builds will not be preserved by default, but an archive with debug information is created.

Pending jobs can be listed:


```
./buildclient.py -v -c demo-config-buildfarm.yaml --list-jobs
```

All jobs (including finished jobs) can be listed as well:

```
./buildclient.py -v -c demo-config-buildfarm.yaml --list-all-jobs
```

A job can be re-queued:

```
./buildclient.py -v -c demo-config-buildfarm.yaml --requeue-job <n>
```
