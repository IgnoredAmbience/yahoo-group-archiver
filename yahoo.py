#!/usr/bin/env python
import requests
import json
import functools
import email
import os
from os.path import basename
from xml.sax.saxutils import unescape

import argparse
import getpass

def unescape_html(string):
    return unescape(string, {"&quot;": '"', "&apos;": "'", "&#39;": "'"})

class YahooGroupsAPI:
    BASE_URI="https://groups.yahoo.com/api/v1/groups/"
    loggedin = False
    s = None

    def __init__(self, group):
        self.s = requests.Session()
        self.group = group
        self.s.headers = {'Referer': self.BASE_URI}

    def __getattr__(self, name):
        """
        Easy, human-readable REST stub, eg:
           yga.messages(123, 'raw')
           yga.messages(count=50)
        """
        return functools.partial(self.get_json, name)

    def login(self, user, password):
        r = self.s.post("https://login.yahoo.com/config/login",
                data={"login":user, "passwd":password}, timeout=10)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
            raise HTTPError(response=r)

    def get_file(self, url):
        r = self.s.get(url)
        r.raise_for_status()
        return r.content

    def download_file(self, url, f, **args):
        r = self.s.get(url, stream=True, **args)
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=4096):
            f.write(chunk)

    def get_json(self, target, *parts, **opts):
        """Get an arbitrary endpoint and parse as json"""
        uri = "/".join([self.BASE_URI, self.group, target] + map(str, parts))
        r = self.s.get(uri, data=opts, allow_redirects=False, timeout=10)
        r.raise_for_status()
        if r.status_code != 200:
            raise HTTPError(response=r)
        return r.json()['ygData']

def archive_email(yga, reattach=True, save=True):
    msg_json = yga.messages()
    count = msg_json['totalRecords']

    msg_json = yga.messages(count=count)
    print "Group has %s messages, got %s" % (count, msg_json['numRecords'])

    for message in msg_json['messages']:
        id = message['messageId']

        print "* Fetching raw message #%d of %d" % (id,count)
        raw_json = yga.messages(str(id), 'raw')
        mime = unescape_html(raw_json['rawEmail']).encode('latin_1', 'ignore')

        eml = email.message_from_string(mime)

        if (save or reattach) and message['hasAttachments']:
            atts = {}
            for attach in message['attachments']:
                print "** Fetching attachment '%s'" % (attach['filename'],)
                atts[attach['filename']] = yga.get_file(attach['link'])

                if save:
                    fname = "%s-%s" % (id, basename(attach['filename']))
                    with file(fname, 'wb') as f:
                        f.write(atts[attach['filename']])

            if reattach:
                for part in eml.walk():
                    fname = part.get_filename()
                    if fname and fname in atts:
                        part.set_payload(atts[fname])
                        email.encoders.encode_base64(part)
                        del atts[fname]

        fname = "%s.eml" % (id,)
        with file(fname, 'w') as f:
            f.write(eml.as_string(unixfrom=False))

def archive_files(yga, subdir=None):
    if subdir:
        json = yga.files(sfpath=subdir)
    else:
        json = yga.files()

    with open('fileinfo.json', 'w') as f:
        f.write(json.dumps(json['dirEntries'], indent=4))

    n = 0
    sz = len(json['dirEntries'])
    for path in json['dirEntries']:
        n = n + 1
        if path['type'] == 0:
            # Regular file
            name = unescape_html(path['fileName'])
            print "* Fetching file '%s' (%d/%d)" % (name, n, sz)
            with open(basename(name), 'wb') as f:
                yga.download_file(path['downloadURL'], f)

        elif path['type'] == 1:
            # Directory
            print "* Fetching directory '%s' (%d/%d)" % (path['fileName'], n, sz)
            with Mkchdir(basename(path['fileName']).replace('.', '')):
                archive_files(yga, subdir=path['pathURI'])

def archive_photos(yga):
    albums = yga.albums()
    n = 0

    for a in albums['albums']:
        n = n + 1
        name = unescape_html(a['albumName'])
        print "* Fetching album '%s' (%d/%d)" % (name, n, albums['total'])

        with Mkchdir(basename(name).replace('.', '')):
            photos = yga.albums(a['albumId'])
            p = 0

            for photo in photos['photos']:
                p = p + 1
                pname = unescape_html(photo['photoName'])
                print "** Fetching photo '%s' (%d/%d)" % (pname, p, photos['total'])

                for info in photo['photoInfo']:
                    if info['photoType'] == 'hr':
                        fname = "%d-%s.jpg" % (photo['photoId'], basename(pname))
                        with open(fname, 'wb') as f:
                            yga.download_file(info['displayURL'], f)

def archive_db(yga):
    json = yga.database()
    n = 0
    nts = len(json['tables'])
    for table in json['tables']:
        n = n + 1
        print "* Downloading database table '%s' (%d/%d)" % (table['name'], n, nts)

        name = basename(table['name']) + '.csv'
        uri = "https://groups.yahoo.com/neo/groups/ulscr/database/%d/records/export?format=csv" % (table['tableId'],)
        with open(name, 'w') as f:
            yga.download_file(uri, f)

class Mkchdir:
    d = ""
    def __init__(self, d):
        self.d = d

    def __enter__(self):
        try:
            os.mkdir(self.d)
        except OSError:
            pass
        os.chdir(self.d)

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir('..')

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument('-u', '--username', type=str)
    p.add_argument('-p', '--password', type=str,
        help='If no password supplied, will be requested on the console')

    pe = p.add_argument_group(title='Email Options')
    pe.add_argument('-r', '--no-reattach', action='store_true',
        help="Don't reattach attachment files to email")
    pe.add_argument('-s', '--no-save', action='store_true',
        help="Don't save email attachments as individual files")

    p.add_argument('group', type=str)

    args = p.parse_args()

    yga = YahooGroupsAPI(args.group)
    if args.username:
        password = args.password or getpass.getpass()
        yga.login(args.username, password)

    with Mkchdir(args.group):
        with Mkchdir('email'):
            archive_email(yga, reattach=(not args.no_reattach), save=(not args.no_save))
        with Mkchdir('files'):
            archive_files(yga)
        with Mkchdir('photos'):
            archive_photos(yga)
        with Mkchdir('databases'):
            archive_db(yga)
