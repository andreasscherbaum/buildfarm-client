import re
import os
import sys
import shutil
import subprocess
import argparse
import logging
#global __urllib_version
_urllib_version = False
try:
    import urllib2
    _urllib_version = 2
except ImportError:
    import urllib3
    _urllib_version = 3
    try:
        import httplib
    except ImportError:
        import http.client as httplib
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import gzip
import zlib
from subprocess import Popen
try: from urlparse import urljoin # Python2
except ImportError: from urllib.parse import urljoin # Python3

# this class must be initialized per repository/branch/revision


class Patch:

    def __init__(self, patches, config, repository, build_dir, cache_dir):
        self.config = config
        self.repository = repository
        self.build_dir = build_dir
        self.cache_dir = cache_dir
        self.patches = patches
        self.patches_applied = False
        self.patches_to_apply = []

        if (len(self.patches) == 0):
            self.patches_applied = True

        return



    # have_patches()
    #
    # quick way to find out if patches are specified
    #
    # parameter:
    #  - self
    # return:
    #  - True/False
    def have_patches(self):
        if (len(self.patches) == 0):
            return False
        else:
            return True



    # remove_patches_after_build()
    #
    # add all potential patches to the delete process
    #
    # parameter:
    #  - self
    #  - build module (contains the cleanup)
    # return:
    #  none
    def remove_patches_after_build(self, build):
        for patch in self.patches_to_apply:
            len_build_dir = len(self.build_dir)
            len_cache_dir = len(self.cache_dir)
            # only remove patches in the build dir or the cache dir
            # never remove patches outside of these two directories
            if (patch[0:len_build_dir] == self.build_dir or patch[0:len_cache_dir] == self.cache_dir):
                build.add_entry_to_delete_clean(patch)
                build.add_entry_to_delete_clean(patch + '.unpacked')



    # apply_patches()
    #
    # apply all specified patches to the build directory
    #
    # parameter:
    #  - self
    # return:
    #  none
    def apply_patches(self):
        if (self.patches_applied == True):
            logging.error("tried to apply patches twice!")
            sys.exit(1)

        logging.debug("patches to apply: " + str(self.patches_to_apply))
        for patch in self.patches_to_apply:
            if not (os.path.isfile(patch)):
                logging.error("Expected patch not found: " + patch)
                return False
            result_patch = self.apply_patch(patch)
            if (result_patch is False):
                # stop applying patches
                return False

        # write a final patch of all the changes
        # first git needs to learn about newly added files
        args = "-C '" + self.build_dir + "' add -N *"
        run = self.repository.run_git(args)
        if (run[0] > 0):
            self.repository.print_git_error(run, args)
            return False

        args = "-C '" + self.build_dir + "' diff"
        run = self.repository.run_git(args)
        if (run[0] > 0):
            self.repository.print_git_error(run, args)
            return False
        # the final diff is in run[1]
        f = open(self.build_dir + '.diff', 'w')
        f.write(run[1].decode())
        f.close()
        logging.info("final patch in: " + self.build_dir + '.diff')

        self.patches_applied = True
        return True



    # apply_patch()
    #
    # apply a single patch
    #
    # parameter:
    #  - self
    #  - path to patch
    # return:
    #  - True/False (False if error)
    def apply_patch(self, patch):
        # try a combination of -p 0, 1 and 2
        # try to unzip the patch, if it's gzipped
        # do a dry run first
        logging.debug("apply patch: " + patch)
        if (self.is_patch_gzipped(patch) is True):
            patch_tmp = self.unpack_patch(patch)
        else:
            patch_tmp = patch

        found_depth = False
        for depth in [1, 0, 2]:
            args = "-C '" + self.build_dir + "' apply --check -p" + str(depth) + " --ignore-whitespace --verbose --recount '" + patch_tmp + "'"
            run = self.repository.run_git(args)
            if (run[0] == 0):
                found_depth = depth
                break

        if (found_depth is False):
            logging.error("not able to apply patch: " + patch)
            return False
        logging.debug("patch depth level: " + str(found_depth))
        args = "-C '" + self.build_dir + "' apply -p" + str(found_depth) + " --ignore-whitespace --verbose --recount '" + patch_tmp + "'"
        run = self.repository.run_git(args)
        # FIXME write out debugging information?
        if (run[0] > 0):
            self.repository.print_git_error(run, args)
            return False

        return True


    # retrieve_patches()
    #
    # retrieve all specified patches
    #
    # parameter:
    #  - self
    # return:
    #  none
    def retrieve_patches(self):
        for patch in self.patches:
            logging.debug("retrieve patch: " + patch)
            patch_path = self.retrieve_patch(patch)
            if (patch_path is False):
                # stop retrieving patches
                return False
            for p in patch_path:
                self.patches_to_apply.append(p)

        return True



    # retrieve_patch()
    #
    # retrieve a single patch
    #
    # parameter:
    #  - self
    #  - path to patch (relative, absolute, url)
    # return:
    #  - False (if error)
    #  - path to local patch file
    def retrieve_patch(self, patch):
        if (os.path.isfile(patch)):
            patch_name = [os.path.abspath(patch)]

        elif (patch[0:19] == 'https://github.com/' and patch.find('/pull/') != -1):
            logging.debug("found GitHub Pull Request")
            patch_name = self.download_pull_request(patch)

        elif (patch[0:34] == 'https://commitfest.postgresql.org/'):
            # cannot directly use the commitfest links, patches might appear multiple times
            logging.error("Cannot use CommitFest links")
            logging.error("Please select a link to a patch from this page")
            return False

        elif (patch[0:37] == 'http://www.postgresql.org/message-id/' or patch[0:38] == 'https://www.postgresql.org/message-id/'):
            if (patch.find('/attachment/') != -1):
                logging.debug("found patch in PostgreSQL archive")
                patch_name = self.download_postgresql_patch_from_archive(patch)
            else:
                logging.debug("found mail message in PostgreSQL archive")
                patch_name = self.download_postgresql_message(patch)

        elif (patch.find('@') != -1):
            logging.debug("looks like a message in the PostgreSQL archive")
            patch_name = self.download_postgresql_message('http://www.postgresql.org/message-id/' + patch + '/')

        elif (patch[0:66] == 'http://git.postgresql.org/gitweb/?p=postgresql.git;a=commitdiff;h=' or patch[0:67] == 'https://git.postgresql.org/gitweb/?p=postgresql.git;a=commitdiff;h='):
            logging.debug("found patch in PostgreSQL git Repository")
            patch_name = self.download_postgresql_patch_from_git(patch)

        elif (patch[0:62] == 'http://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=' or patch[0:63] == 'https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h='):
            logging.debug("found patch info in PostgreSQL git Repository")
            patch_name = self.download_postgresql_patch_info_from_git(patch)

        elif (len(patch) == 40 and re.search(r'^[a-f0-9]+$', patch)):
            logging.debug("found potential patch in PostgreSQL git Repository")
            patch_name = self.download_postgresql_patch_from_git('http://git.postgresql.org/gitweb/?p=postgresql.git;a=commitdiff;h=' + patch)

        else:
            logging.error("Can't identify type of patch!")
            logging.error("Argument: " + patch)
            return False

        # Test case with 1 attachment:
        #   http://www.postgresql.org/message-id/56AFBEF5.102@wars-nicht.de
        # Test case just the patch
        #   http://www.postgresql.org/message-id/attachment/41737/64bit_3.diff
        # Test case with many attachments:
        #   http://www.postgresql.org/message-id/20150831225328.GM2912@alvherre.pgsql

        # FIXME: mail message in Greenplum archive

        if (len(patch_name) == 0):
            logging.error("No patches found in: " + patch)
            sys.exit(1)

        for entry in patch_name:
            if (os.path.isfile(entry)):
                if (os.stat(entry).st_size == 0):
                    logging.error("Empty patch: " + str(entry))
                    sys.exit(1)


        return patch_name



    # download_pull_request()
    #
    # download a GitHub pull request
    #
    # parameter:
    #  - self
    #  - PR url
    # return:
    #  - local filename of patch (list)
    def download_pull_request(self, url):
        hashname = self.config.create_hashname(url)

        # Github returns the raw patch if the url ends in PR + .diff or .patch
        data = self.download_url(url + '.diff')
        patch_name = os.path.join(self.cache_dir, hashname + '.diff')
        f = open(patch_name, 'w')
        f.write(data)
        f.close()
        logging.debug("patch from PR " + url + " saved under: " + patch_name)

        return [patch_name]



    # download_postgresql_patch_from_archive()
    #
    # download a patch from the PostgreSQL archive
    #
    # parameter:
    #  - self
    #  - patch url
    # return:
    #  - local filename of patch (list)
    def download_postgresql_patch_from_archive(self, url):
        hashname = self.config.create_hashname(url)

        data = self.download_url(url)
        patch_name = os.path.join(self.cache_dir, hashname + '.diff')
        f = open(patch_name, 'w')
        f.write(data)
        f.close()
        logging.debug("patch from url " + url + " saved under: " + patch_name)

        return [patch_name]



    # download_postgresql_message()
    #
    # download all patches from a mail in the PostgreSQL archive
    #
    # parameter:
    #  - self
    #  - mail message url
    # return:
    #  - local filename of patches (list)
    def download_postgresql_message(self, url):
        hashname = self.config.create_hashname(url)
        # the PostgreSQL mail archive lists all attachments with "Attachment:"
        # can have multiple entries

        # fetch the message first
        message = self.download_url(url)

        attachment_number = 0
        attachments = []
        line_name_template = os.path.join(self.cache_dir, hashname + '_')

        for line in message.splitlines():
            #print("" + line + os.linesep)
            line_match = re.search(r'Attachment:.+?<a href=\"(.+?)\">', line)
            if (line_match):
                # found attachment
                line_url = urljoin(url, line_match.group(1))
                logging.debug("found attachment: " + line_url)
                line_attachment = self.download_url(line_url)
                attachment_number += 1
                line_name = line_name_template + str(attachment_number).zfill(3) + '.diff'
                f = open(line_name, 'w')
                f.write(line_attachment)
                f.close()
                attachments.append(line_name)

        if (len(attachments) == 0):
            #logging.debug("no patches found in url " + url)
            pass
        elif (len(attachments) == 1):
            logging.debug("patch from url " + url + " saved under: " + line_name_template + "*.diff")
        else:
            logging.debug("patches from url " + url + " saved under: " + line_name_template + "*.diff")

        return attachments



    # download_postgresql_patch_from_git()
    #
    # download a patch from the PostgreSQL git Repository
    #
    # parameter:
    #  - self
    #  - git Repository url
    # return:
    #  - local filename of patches (list)
    def download_postgresql_patch_from_git(self, url):
        hashname = self.config.create_hashname(url)
        # the 'raw' link points to a somewhat raw version of the diff
        # with some additional text on the top

        # fetch the entry first
        message = self.download_url(url)

        raw_link = False
        attachments = []
        patch_name = os.path.join(self.cache_dir, hashname + '.diff')

        for line in message.splitlines():
            #print("" + line + os.linesep)
            line_match = re.search(r'^<a href=\"(.+?commitdiff_plain.*?)\">raw</a>', line)
            if (line_match):
                # found attachment
                line_url = urljoin(url, line_match.group(1))
                logging.debug("found link to raw patch: " + line_url)
                line_attachment = self.download_url(line_url)
                f = open(patch_name, 'w')

                in_patch_pos = 0
                for line2 in line_attachment.splitlines():
                    if (in_patch_pos == 0 and line2[0:3] == '---'):
                        in_patch_pos = 1
                    if (in_patch_pos == 1 and len(line2) == 0):
                        in_patch_pos = 2
                    if (in_patch_pos == 2 and line2[0:5] == 'diff '):
                        in_patch_pos = 3

                    if (in_patch_pos == 3):
                        f.write(line2 + os.linesep)

                f.close()
                logging.debug("patch from url " + url + " saved under: " + patch_name)

                return [patch_name]

        if (len(attachments) == 0):
            logging.debug("no patches found in url " + url)
            pass
        elif (len(attachments) == 1):
            logging.debug("patch from url " + url + " saved under: " + patch_name)
        else:
            logging.error("found too many patches in url: " + url)
            sys.exit(1)

        return attachments



    # download_postgresql_patch_info_from_git()
    #
    # download a patch from the info page from the PostgreSQL git Repository
    #
    # parameter:
    #  - self
    #  - git Repository info url
    # return:
    #  - local filename of patches (list)
    def download_postgresql_patch_info_from_git(self, url):
        # fetch the entry first
        message = self.download_url(url)

        for line in message.splitlines():
            #print("" + line + os.linesep)
            line_match = re.search(r'<a href=\"(/gitweb/\?p=postgresql\.git;a=commitdiff;h=[a-f0-9]+)\">commitdiff</a>', line)
            if (line_match):
                # found commitdiff
                line_url = urljoin(url, line_match.group(1))
                logging.debug("found link to commitdiff: " + line_url)
                return self.download_postgresql_patch_from_git(line_url)

        logging.error("no commitdiff found in url: " + url)
        sys.exit(1)



    # download_url()
    #
    # download a specific url, handle compression
    #
    # parameter:
    #  - self
    #  - url
    # return:
    #  - content of the link
    def download_url(self, url):
        global _urllib_version

        # patches are only used in interactive mode
        # it's ok to break here if something does not work as expected
        if (_urllib_version == 2):
            rq = urllib2.Request(url)
            rq.add_header('Accept-encoding', 'gzip')

            try:
                rs = urllib2.urlopen(rq)
            except urllib2.HTTPError as e:
                if (e.code == 400):
                    logging.error('HTTPError = ' + str(e.code) + ' (Bad Request)')
                elif (e.code == 401):
                    logging.error('HTTPError = ' + str(e.code) + ' (Unauthorized)')
                elif (e.code == 403):
                    logging.error('HTTPError = ' + str(e.code) + ' (Forbidden)')
                elif (e.code == 404):
                    logging.error('HTTPError = ' + str(e.code) + ' (URL not found)')
                elif (e.code == 408):
                    logging.error('HTTPError = ' + str(e.code) + ' (Request Timeout)')
                elif (e.code == 418):
                    logging.error('HTTPError = ' + str(e.code) + " (I'm a teapot)")
                elif (e.code == 500):
                    logging.error('HTTPError = ' + str(e.code) + ' (Internal Server Error)')
                elif (e.code == 502):
                    logging.error('HTTPError = ' + str(e.code) + ' (Bad Gateway)')
                elif (e.code == 503):
                    logging.error('HTTPError = ' + str(e.code) + ' (Service Unavailable)')
                elif (e.code == 504):
                    logging.error('HTTPError = ' + str(e.code) + ' (Gateway Timeout)')
                else:
                    logging.error('HTTPError = ' + str(e.code))
                sys.exit(1)
            except urllib2.URLError as e:
                logging.error('URLError = ' + str(e.reason))
                sys.exit(1)
            except httplib.HTTPException as e:
                logging.error('HTTPException')
                sys.exit(1)
            except Exception:
                logging.error('generic exception')
                sys.exit(1)

            if rs.info().get('Content-Encoding') == 'gzip':
                b = StringIO(rs.read())
                f = gzip.GzipFile(fileobj = b)
                data = f.read()
            else:
                data = rs.read()

        elif (_urllib_version == 3):
            logging.getLogger("urllib3").setLevel(logging.WARNING)
            logging.getLogger("httplib").setLevel(logging.WARNING)
            user_agent = {'user-agent': 'GPDB buildclient', 'accept-encoding': 'gzip, deflate'}
            #http = urllib3.PoolManager(maxsize = 3, retries = 2, headers = user_agent)
            http = urllib3.PoolManager(maxsize = 3, headers = user_agent)

            try:
                rs = http.urlopen('GET', url, redirect = True)
            except urllib3.exceptions.MaxRetryError as e:
                logging.error("Too many retries")
                sys.exit(1)
            except urllib3.URLError as e:
                logging.error('URLError = ' + str(e.code))
                sys.exit(1)
            except httplib.HTTPException as e:
                logging.error('HTTPException')
                sys.exit(1)
            except urllib3.exceptions.ConnectTimeoutError as e:
                logging.error("Timeout")
                sys.exit(1)
            except Exception:
                logging.error('generic exception')
                sys.exit(1)

            if (rs.status != 200):
                if (rs.status == 400):
                    logging.error("HTTPError = 400 (Bad Request)")
                elif (rs.status == 401):
                    logging.error("HTTPError = 401 (Unauthorized)")
                elif (rs.status == 403):
                    logging.error("HTTPError = 403 (Forbidden)")
                elif (rs.status == 404):
                    logging.error("HTTPError = 404 (URL not found)")
                elif (rs.status == 408):
                    logging.error("HTTPError = 408 (Request Timeout)")
                elif (rs.status == 418):
                    logging.error("HTTPError = 418 (I'm a teapot)")
                elif (rs.status == 500):
                    logging.error("HTTPError = 500 (Internal Server Error)")
                elif (rs.status == 502):
                    logging.error("HTTPError = 502 (Bad Gateway)")
                elif (rs.status == 503):
                    logging.error("HTTPError = 503 (Service Unavailable)")
                elif (rs.status == 504):
                    logging.error("HTTPError = 504 (Gateway Timeout)")
                else:
                    logging.error("HTTPError = " + str(rs.status) + "")
                sys.exit(1)

            if (len(rs.data.decode()) == 0):
                logging.error("failed to download the patch")
                sys.exit(1)

            data = rs.data.decode()

        else:
            logging.error("unknown urllib version!")
            sys.exit(1)


        logging.debug("fetched " + self.config.human_size(len(data)))

        return data



    # is_patch_gzipped()
    #
    # figures out if a local patch file is gzipped
    #
    # parameter:
    #  - self
    #  - path to patch file
    # return:
    #  - True/False
    def is_patch_gzipped(self, file):
        f = open(file, 'rb')
        data = f.read()
        f.close()

        # try to uncompress the file (only gzip)
        try:
            data_out = zlib.decompress(data)
            return True
        except zlib.error:
            pass

        try:
            data_out = zlib.decompress(data, -zlib.MAX_WBITS)
            return True
        except zlib.error:
            pass
        try:
            data_out = zlib.decompress(data, zlib.MAX_WBITS|16)
            return True
        except zlib.error:
            pass

        return False



    # unpack_patch()
    #
    # unpack a gzipped patch
    #
    # parameter:
    #  - self
    #  - path to patch file
    # return:
    #  - path to unpacked patch file
    def unpack_patch(self, file):
        new_name = file + '.unpacked'
        f = open(file, 'rb')
        data = f.read()
        f.close()

        # try to uncompress the file (only gzip)
        try:
            data_out = zlib.decompress(data)
        except zlib.error:
            try:
                data_out = zlib.decompress(data, -zlib.MAX_WBITS)
            except zlib.error:
                try:
                    data_out = zlib.decompress(data, zlib.MAX_WBITS|16)
                except zlib.error:
                    logging.error("Can't unpack the file: " + file)
                    sys.exit(1)

        f = open(new_name, 'wb')
        f.write(data_out)
        f.close()

        logging.debug("unpack " + file + " to " + new_name + " (" + self.config.human_size(len(data)) + " / " + self.config.human_size(len(data_out)) + ")")

        return new_name





