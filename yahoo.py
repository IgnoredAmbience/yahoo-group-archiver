#!/usr/bin/env python
from yahoogroupsapi import YahooGroupsAPI
import json
import email
import urllib
import os
from os.path import basename
from xml.sax.saxutils import unescape
import argparse
import getpass
import sys
import requests

def unescape_html(string):
    return unescape(string, {"&quot;": '"', "&apos;": "'", "&#39;": "'"})

def get_best_photoinfo(photoInfoArr, exclude=[]):
    rs = {'tn': 0, 'sn': 1, 'hr': 2, 'or': 3}

    # exclude types we're not interested in
    for x in exclude:
        if x in rs:
            rs[x] = -1

    best = photoInfoArr[0]
    for info in photoInfoArr:
        if info['photoType'] not in rs:
            print "ERROR photoType '%s' not known" % info['photoType']
            continue
        if rs[info['photoType']] >= rs[best['photoType']]:
            best = info
    if rs[best['photoType']] == -1:
        return None
    else:
        return best


def archive_email(yga, reattach=True, save=True):
    msg_json = yga.messages()
    count = msg_json['totalRecords']

    msg_json = yga.messages(count=count)
    print "Group has %s messages, got %s" % (count, msg_json['numRecords'])

    for message in msg_json['messages']:
        id = message['messageId']

        print "* Fetching raw message #%d of %d" % (id,count)
        raw_json = yga.messages(id, 'raw')
        mime = unescape_html(raw_json['rawEmail']).encode('latin_1', 'ignore')

        eml = email.message_from_string(mime)

        if (save or reattach) and message['hasAttachments']:
            atts = {}
            if not 'attachments' in message:
                print "** Yahoo says this message has attachments, but I can't find any!"
            else:
                for attach in message['attachments']:
                    print "** Fetching attachment '%s'" % (attach['filename'],)
                    if 'link' in attach:
                        # try and download the attachment
                        # (sometimes yahoo doesn't keep them)
                        try:
                            atts[attach['filename']] = yga.get_file(attach['link'])
                        except requests.exceptions.HTTPError as err:
                            print "ERROR: can't download attachment: %s" % err
                            continue

                    elif 'photoInfo' in attach:
                        # keep retrying until we find the largest image size we can download
                        # (sometimes yahoo doesn't keep the originals)
                        exclude = []
                        ok = False
                        while not ok:
                            # find best photoinfo (largest size)
                            photoinfo = get_best_photoinfo(attach['photoInfo'], exclude)

                            if photoinfo is None:
                                print("ERROR: can't find a viable copy of this photo")
                                break

                            # try and download it
                            try:
                                atts[attach['filename']] = yga.get_file(photoinfo['displayURL'])
                                ok = True
                            except requests.exceptions.HTTPError as err:
                                # yahoo says no. exclude this size and try for another.
                                print "ERROR downloading '%s' variant: %s" % (photoinfo['photoType'], err)
                                exclude.append(photoinfo['photoType'])

                        # if we failed, try the next attachment
                        if not ok:
                            continue

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
        file_json = yga.files(sfpath=subdir)
    else:
        file_json = yga.files()

    with open('fileinfo.json', 'w') as f:
        f.write(json.dumps(file_json['dirEntries'], indent=4))

    n = 0
    sz = len(file_json['dirEntries'])
    for path in file_json['dirEntries']:
        n += 1
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
                pathURI = urllib.unquote(path['pathURI'])
                archive_files(yga, subdir=pathURI)

def archive_photos(yga):
    albums = yga.albums()
    n = 0

    for a in albums['albums']:
        n += 1
        name = unescape_html(a['albumName'])
        # Yahoo has an off-by-one error in the album count...
        print "* Fetching album '%s' (%d/%d)" % (name, n, albums['total'] - 1)

        with Mkchdir(basename(name).replace('.', '')):
            photos = yga.albums(a['albumId'])
            p = 0

            for photo in photos['photos']:
                p += 1
                pname = unescape_html(photo['photoName'])
                print "** Fetching photo '%s' (%d/%d)" % (pname, p, photos['total'])

                photoinfo = get_best_photoinfo(photo['photoInfo'])
                fname = "%d-%s.jpg" % (photo['photoId'], basename(pname))
                with open(fname, 'wb') as f:
                    yga.download_file(photoinfo['displayURL'], f)

def archive_db(yga, group):
    json = yga.database()
    n = 0
    nts = len(json['tables'])
    for table in json['tables']:
        n += 1
        print "* Downloading database table '%s' (%d/%d)" % (table['name'], n, nts)

        name = basename(table['name']) + '.csv'
        uri = "https://groups.yahoo.com/neo/groups/%s/database/%s/records/export?format=csv" % (group, table['tableId'])
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
    p.add_argument('-ct', '--cookie_t', type=str)
    p.add_argument('-cy', '--cookie_y', type=str)

    po = p.add_argument_group(title='What to archive', description='By default, all the below.')
    po.add_argument('-e', '--email', action='store_true',
            help='Only archive email and attachments')
    po.add_argument('-f', '--files', action='store_true',
            help='Only archive files')
    po.add_argument('-i', '--photos', action='store_true',
            help='Only archive photo galleries')
    po.add_argument('-d', '--database', action='store_true',
            help='Only archive database')

    pe = p.add_argument_group(title='Email Options')
    pe.add_argument('-r', '--no-reattach', action='store_true',
            help="Don't reattach attachment files to email")
    pe.add_argument('-s', '--no-save', action='store_true',
            help="Don't save email attachments as individual files")

    p.add_argument('group', type=str)

    args = p.parse_args()

    yga = YahooGroupsAPI(args.group, args.cookie_t, args.cookie_y)
    if args.username:
        password = args.password or getpass.getpass()
        print "logging in..."
        if not yga.login(args.username, password):
            print "Login failed"
            sys.exit(1)

    if not (args.email or args.files or args.photos or args.database):
        args.email = args.files = args.photos = args.database = True

    with Mkchdir(args.group):
        if args.email:
            with Mkchdir('email'):
                archive_email(yga, reattach=(not args.no_reattach), save=(not args.no_save))
        if args.files:
            with Mkchdir('files'):
                archive_files(yga)
        if args.photos:
            with Mkchdir('photos'):
                archive_photos(yga)
        if args.database:
            with Mkchdir('databases'):
                archive_db(yga, args.group)
