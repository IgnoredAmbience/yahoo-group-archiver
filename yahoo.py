#!/usr/bin/env python
from __future__ import unicode_literals
import yahoogroupsapi
from yahoogroupsapi import YahooGroupsAPI

import argparse
import codecs
import datetime
import json
import logging
import math
import os
import re
import requests.exceptions
import time
import sys
import unicodedata
from os.path import basename
from collections import OrderedDict
from requests.cookies import RequestsCookieJar, create_cookie


if (sys.version_info < (3, 0)):
    from cookielib import LWPCookieJar
    from urllib import unquote
    from HTMLParser import HTMLParser
    hp = HTMLParser()
    html_unescape = hp.unescape
    text = unicode  # noqa: F821
else:
    from http.cookiejar import LWPCookieJar
    from urllib.parse import unquote
    from html import unescape as html_unescape
    text = str

# WARC metadata params

WARC_META_PARAMS = OrderedDict([('software', 'yahoo-group-archiver'),
                                ('version', '20191025-1'),
                                ('format', 'WARC File Format 1.0'),
                                ])


def get_best_photoinfo(photoInfoArr, exclude=[]):
    logger = logging.getLogger(name="get_best_photoinfo")
    rs = {'tn': 0, 'sn': 1, 'hr': 2, 'or': 3}

    # exclude types we're not interested in
    for x in exclude:
        if x in rs:
            rs[x] = -1

    best = photoInfoArr[0]
    for info in photoInfoArr:
        if info['photoType'] not in rs:
            logger.error("photoType '%s' not known", info['photoType'])
            continue
        if rs[info['photoType']] >= rs[best['photoType']]:
            best = info
    if rs[best['photoType']] == -1:
        return None
    else:
        return best


def archive_messages_metadata(yga):
    logger = logging.getLogger('archive_message_metadata')
    params = {'sortOrder': 'asc', 'direction': 1, 'count': 1000}

    message_ids = []
    next_page_start = float('inf')
    page_count = 0

    logger.info("Archiving message metadata...")
    last_next_page_start = 0

    while next_page_start > 0:
        msgs = yga.messages(**params)
        with open("message_metadata_%s.json" % page_count, 'wb') as f:
            json.dump(msgs, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

        message_ids += [msg['messageId'] for msg in msgs['messages']]

        logger.info("Archived message metadata records (%d of %d)", len(message_ids), msgs['totalRecords'])

        page_count += 1
        next_page_start = params['start'] = msgs['nextPageStart']
        if next_page_start == last_next_page_start:
            break
        last_next_page_start = next_page_start

    return message_ids


def archive_message_content(yga, id, status=""):
    logger = logging.getLogger('archive_message_content')
    try:
        logger.info("Fetching  raw message id: %d %s", id, status)
        raw_json = yga.messages(id, 'raw')
        fname = "%s_raw.json" % (id,)
        with open(fname, 'wb') as f:
            json.dump(raw_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        set_mtime(fname, int(raw_json['postDate']))
    except Exception:
        logger.exception("Raw grab failed for message %d", id)

    try:
        logger.info("Fetching html message id: %d %s", id, status)
        html_json = yga.messages(id)
        fname = "%s.json" % (id,)
        with open(fname, 'wb') as f:
            json.dump(html_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        set_mtime(fname, int(html_json['postDate']))

        if 'attachmentsInfo' in html_json and len(html_json['attachmentsInfo']) > 0:
            with Mkchdir("%d_attachments" % id):
                process_single_attachment(yga, html_json['attachmentsInfo'])
            set_mtime(sanitise_folder_name("%d_attachments" % id), int(html_json['postDate']))
    except Exception:
        logger.exception("HTML grab failed for message %d", id)


def archive_email(yga, message_subset=None, start=None, stop=None):
    logger = logging.getLogger('archive_email')
    try:
        # Grab messages for initial counts and permissions check
        init_messages = yga.messages()
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Messages functionality for this group")
        return
    except Exception:
        logger.exception("Unknown error archiving messages")
        return

    if start is not None or stop is not None:
        start = start or 1
        stop = stop or init_messages['lastRecordId']
        stop = min(stop, init_messages['lastRecordId'])
        r = range(start, stop + 1)

        if message_subset is None:
            message_subset = list(r)
        else:
            s = set(r).union(message_subset)
            message_subset = list(s)
            message_subset.sort()

    if not message_subset:
        message_subset = archive_messages_metadata(yga)
        logger.info("Group has %s messages (maximum id: %s), fetching all",
                    len(message_subset), (message_subset or ['n/a'])[-1])

    n = 1
    for id in message_subset:
        status = "(%d of %d)" % (n, len(message_subset))
        n += 1
        try:
            archive_message_content(yga, id, status)
        except Exception:
            logger.exception("Failed to get message id: %d", id)
            continue


def process_single_attachment(yga, attach):
    logger = logging.getLogger(name="process_single_attachment")
    for frec in attach:
        logger.info("Fetching attachment '%s'", frec['filename'])
        fname = "%s-%s" % (frec['fileId'], frec['filename'])
        ffname = sanitise_file_name(fname)
        with open(ffname, 'wb') as f:
            if 'link' in frec:
                # try and download the attachment
                # (sometimes yahoo doesn't keep them)
                ok = True
                try:
                    yga.download_file(frec['link'], f=f)
                except requests.exceptions.HTTPError as err:
                    logger.error("ERROR downloading attachment '%s': %s", frec['link'], err)

            elif 'photoInfo' in frec:
                # keep retrying until we find the largest image size we can download
                # (sometimes yahoo doesn't keep the originals)
                exclude = []
                ok = False
                while not ok:
                    # find best photoinfo (largest size)
                    photoinfo = get_best_photoinfo(frec['photoInfo'], exclude)

                    if photoinfo is None:
                        logger.error("Can't find a viable copy of this photo")
                        break

                    # try and download it
                    try:
                        yga.download_file(photoinfo['displayURL'], f=f)
                        ok = True
                    except requests.exceptions.HTTPError as err:
                        # yahoo says no. exclude this size and try for another.
                        logger.error("ERROR downloading '%s' variant %s: %s", photoinfo['displayURL'],
                                     photoinfo['photoType'], err)
                        # exclude.append(photoinfo['photoType'])

            # if we failed, try the next attachment
            if not ok:
                continue
        set_mtime(ffname, frec['modificationDate'])


def archive_files(yga, subdir=None):
    logger = logging.getLogger(name="archive_files")
    try:
        if subdir:
            file_json = yga.files(sfpath=subdir)
        else:
            file_json = yga.files()
    except Exception:
        logger.error("Couldn't access Files functionality for this group")
        return

    with open('fileinfo.json', 'wb') as f:
        json.dump(file_json['dirEntries'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    n = 0
    sz = len(file_json['dirEntries'])
    for path in file_json['dirEntries']:
        n += 1
        if path['type'] == 0:
            # Regular file
            name = html_unescape(path['fileName'])
            new_name = sanitise_file_name("%d_%s" % (n, name))
            logger.info("Fetching file '%s' as '%s' (%d/%d)", name, new_name, n, sz)
            with open(new_name, 'wb') as f:
                yga.download_file(path['downloadURL'], f)
            set_mtime(new_name, path['createdTime'])

        elif path['type'] == 1:
            # Directory
            name = html_unescape(path['fileName'])
            new_name = "%d_%s" % (n, name)
            logger.info("Fetching directory '%s' as '%s' (%d/%d)", name, sanitise_folder_name(new_name), n, sz)
            with Mkchdir(new_name):     # (new_name sanitised again by Mkchdir)
                pathURI = unquote(path['pathURI'])
                archive_files(yga, subdir=pathURI)
            set_mtime(sanitise_folder_name(new_name), path['createdTime'])


def archive_attachments(yga):
    logger = logging.getLogger(name="archive_attachments")
    try:
        attachments_json = yga.attachments()
    except Exception:
        logger.error("Couldn't access Attachments functionality for this group")
        return

    with open('allattachmentinfo.json', 'wb') as f:
        json.dump(attachments_json['attachments'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    n = 0
    for a in attachments_json['attachments']:
        n += 1
        with Mkchdir(a['attachmentId']):
            try:
                a_json = yga.attachments(a['attachmentId'])
            except Exception:
                logger.error("Attachment id %d inaccessible.", a['attachmentId'])
                continue
            with open('attachmentinfo.json', 'wb') as f:
                json.dump(a_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
                process_single_attachment(yga, a_json['files'])
        set_mtime(sanitise_folder_name(a['attachmentId']), a['modificationDate'])


def archive_photos(yga):
    logger = logging.getLogger(name="archive_photos")
    try:
        nb_albums = yga.albums(count=5)['total'] + 1
    except Exception:
        logger.error("Couldn't access Photos functionality for this group")
        return
    albums = yga.albums(count=nb_albums)
    n = 0

    with open('albums.json', 'wb') as f:
        json.dump(albums['albums'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    for a in albums['albums']:
        n += 1
        name = html_unescape(a['albumName'])
        # Yahoo sometimes has an off-by-one error in the album count...
        logger.info("Fetching album '%s' (%d/%d)", name, n, albums['total'])

        folder = "%d-%s" % (a['albumId'], name)

        with Mkchdir(folder):
            photos = yga.albums(a['albumId'])
            pages = int(photos['total'] / 100 + 1)
            p = 0

            for page in range(pages):
                photos = yga.albums(a['albumId'], start=page*100, count=100)
                with open('photos-%d.json' % page, 'wb') as f:
                    json.dump(photos['photos'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

                for photo in photos['photos']:
                    p += 1
                    pname = html_unescape(photo['photoName'])
                    logger.info("Fetching photo '%s' (%d/%d)", pname, p, photos['total'])

                    photoinfo = get_best_photoinfo(photo['photoInfo'])
                    fname = "%d-%s.jpg" % (photo['photoId'], pname)
                    ffname = sanitise_file_name(fname)
                    with open(ffname, 'wb') as f:
                        try:
                            yga.download_file(photoinfo['displayURL'], f)
                        except requests.exceptions.HTTPError:
                            logger.error("HTTP error, unable to download, out of retries")
                    set_mtime(ffname, photo['creationDate'])
        set_mtime(sanitise_folder_name(folder), a['modificationDate'])


def archive_db(yga):
    logger = logging.getLogger(name="archive_db")
    try:
        db_json = yga.database()
    except yahoogroupsapi.AuthenticationError:
        db_json = None
        # 401 or 403 error means Permission Denied; 307 means redirect to login. Retrying won't help.
        logger.error("Couldn't access Database functionality for this group")
        return

    with open('databases.json', 'wb') as f:
        json.dump(db_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    n = 0
    nts = len(db_json['tables'])
    for table in db_json['tables']:
        n += 1
        try:
            logger.info("Downloading database table '%s' (%d/%d)", table['name'], n, nts)

            name = "%s_%s.csv" % (table['tableId'], table['name'])
            uri = "https://groups.yahoo.com/neo/groups/%s/database/%s/records/export?format=csv" % (yga.group, table['tableId'])

            with open(sanitise_file_name(name), 'wb') as f:
                yga.download_file(uri, f)
            set_mtime(sanitise_file_name(name), table['dateLastModified'])

            records_json = yga.database(table['tableId'], 'records')
            with open('%s_records.json' % table['tableId'], 'wb') as f:
                json.dump(records_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
            set_mtime('%s_records.json' % table['tableId'], table['dateLastModified'])
        except Exception:
            logger.exception("Failed to get table '%s' (%d/%d)", table['name'], n, nts)
            continue


def archive_links(yga, subdir=''):
    logger = logging.getLogger(name="archive_links")

    try:
        links = yga.links(linkdir=subdir)
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Links functionality for this group")
        return

    with open('links.json', 'wb') as f:
        json.dump(links, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        logger.info("Written %d links from %s folder", links['numLink'], subdir)

    n = 0
    for a in links['dirs']:
        n += 1
        logger.info("Fetching links folder '%s' (%d/%d)", a['folder'], n, links['numDir'])

        with Mkchdir(a['folder']):
            archive_links(yga, "%s/%s" % (subdir, a['folder']))


def archive_calendar(yga):
    logger = logging.getLogger(name="archive_calendar")
    groupinfo = yga.HackGroupInfo()

    if 'entityId' not in groupinfo:
        logger.error("Couldn't download calendar/events: missing entityId")
        return

    entityId = groupinfo['entityId']

    api_root = "https://calendar.yahoo.com/ws/v3"

    # We get the wssid
    tmpUri = "%s/users/%s/calendars/events/?format=json&dtstart=20000101dtend=20000201&wssid=Dummy" % (api_root, entityId)
    try:
        yga.download_file(tmpUri)  # We expect a 403 or 401  here
        logger.error("Attempt to get wssid returned HTTP 200, which is unexpected!")  # we should never hit this
        return
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403 or e.response.status_code == 401:
            tmpJson = json.loads(e.response.content)['calendarError']
        else:
            logger.error("Attempt to get wssid returned an unexpected response status %d" % e.response.status_code)
            return

    if 'wssid' not in tmpJson:
        logger.error("Couldn't download calendar/events: missing wssid")
        return
    wssid = tmpJson['wssid']

    # Getting everything since the launch of Yahoo! Groups (January 30, 2001)
    archiveDate = datetime.datetime(2001, 1, 30)
    endDate = datetime.datetime(2025, 1, 1)
    while archiveDate < endDate:
        jsonStart = archiveDate.strftime("%Y%m%d")
        jsonEnd = (archiveDate + datetime.timedelta(days=1000)).strftime("%Y%m%d")
        calURL = "%s/users/%s/calendars/events/?format=json&dtstart=%s&dtend=%s&wssid=%s" % \
            (api_root, entityId, jsonStart, jsonEnd, wssid)

        try:
            logger.info("Trying to get events between %s and %s", jsonStart, jsonEnd)
            calContentRaw = yga.download_file(calURL)
        except requests.exception.HTTPError:
            logger.error("Unrecoverable error getting events between %s and %s: URL %s", jsonStart, jsonEnd, calURL)

        calContent = json.loads(calContentRaw)
        if calContent['events']['count'] > 0:
            filename = jsonStart + "-" + jsonEnd + ".json"
            with open(filename, 'wb') as f:
                logger.info("Got %d event(s)", calContent['events']['count'])
                json.dump(calContent, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

        archiveDate += datetime.timedelta(days=1000)


def archive_about(yga):
    logger = logging.getLogger(name="archive_about")
    groupinfo = yga.HackGroupInfo()
    logger.info("Downloading group description data")

    with open('about.json', 'wb') as f:
        json.dump(groupinfo, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    statistics = yga.statistics()

    with open('statistics.json', 'wb') as f:

        json.dump(statistics, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    # Check if we really have a photo in the group description
    if ('photoInfo' in statistics['groupHomePage'] and statistics['groupHomePage']['photoInfo']):
        exclude = []

        # find best photoinfo (largest size)
        photoinfo = get_best_photoinfo(statistics['groupHomePage']['photoInfo'], exclude)

        if photoinfo is not None:
            fname = 'GroupPhoto-%s' % basename(photoinfo['displayURL']).split('?')[0]
            logger.info("Downloading the photo in group description as %s", fname)
            try:
                with open(sanitise_file_name(fname), 'wb') as f:
                    yga.download_file(photoinfo['displayURL'], f)
            except yahoogroupsapi.YGAException:
                logger.error("Unrecoverable error getting group description photo at URL %s", photoinfo['displayURL'])

    if statistics['groupCoverPhoto']['hasCoverImage']:
        exclude = []

        # find best photoinfo (largest size)
        photoinfo = get_best_photoinfo(statistics['groupCoverPhoto']['photoInfo'], exclude)

        if photoinfo is not None:
            fname = 'GroupCover-%s' % basename(photoinfo['displayURL']).split('?')[0]
            logger.info("Downloading the group cover as %s", fname)
            try:
                with open(sanitise_file_name(fname), 'wb') as f:
                    yga.download_file(photoinfo['displayURL'], f)
            except yahoogroupsapi.YGAException:
                logger.error("Unrecoverable error getting group cover photo at URL %s", photoinfo['displayURL'])


def archive_polls(yga):
    logger = logging.getLogger(name="archive_polls")
    try:
        pollsList = yga.polls(count=100, sort='DESC')
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Polls functionality for this group")
        return

    if len(pollsList) == 100:
        logger.info("Got 100 polls, checking if there are more ...")
        endoflist = False
        offset = 99

        while not endoflist:
            tmpList = yga.polls(count=100, sort='DESC', start=offset)
            tmpCount = len(tmpList)
            logger.info("Got %d more polls", tmpCount)

            # Trivial case first
            if tmpCount < 100:
                endoflist = True

            # Again we got 100 polls, increase the offset
            if tmpCount == 100:
                offset += 99

            # Last survey
            if pollsList[len(pollsList)-1]['surveyId'] == tmpList[len(tmpList)-1]['surveyId']:
                logger.info("No new polls found with offset %d", offset)
                endoflist = True
                break

            pollsList += tmpList

    totalPolls = len(pollsList)
    logger.info("Found %d polls to grab", totalPolls)

    n = 0
    for p in pollsList:
        n += 1
        try:
            logger.info("Downloading poll %d [%d/%d]", p['surveyId'], n, totalPolls)
            pollInfo = yga.polls(p['surveyId'])
            fname = '%s-%s.json' % (n, p['surveyId'])

            with open(fname, 'wb') as f:
                json.dump(pollInfo, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
            set_mtime(fname, pollInfo['dateCreated'])
        except Exception:
            logger.exception("Failed to get poll %d [%d/%d]", p['surveyId'], n, totalPolls)
            continue



def archive_members(yga):
    logger = logging.getLogger(name="archive_members")
    try:
        confirmed_json = yga.members('confirmed')
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Members list functionality for this group")
        return
    n_members = confirmed_json['total']
    # we can dump 100 member records at a time
    all_members = []
    for i in range(int(math.ceil(n_members)/100 + 1)):
        confirmed_json = yga.members('confirmed', start=100*i, count=100)
        all_members = all_members + confirmed_json['members']
        with open('memberinfo_%d.json' % i, 'wb') as f:
            json.dump(confirmed_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    all_json_data = {"total": n_members, "members": all_members}
    with open('allmemberinfo.json', 'wb') as f:
        json.dump(all_json_data, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    logger.info("Saved members: Expected: %d, Actual: %d", n_members, len(all_members))


####
# Utility Functions
####

def set_mtime(path, mtime):
    """
    Sets the last-modified date of a file or directory
    """
    atime = time.time()
    os.utime(path, (atime, mtime))

def sanitise_file_name(value):
    """
    Convert spaces to hyphens.  Remove characters that aren't alphanumerics, underscores, periods or hyphens.
    Also strip leading and trailing whitespace and periods.
    """
    value = text(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s.-]', '', value).strip().strip('.')
    return re.sub(r'[-\s]+', '-', value)


def sanitise_folder_name(name):
    return sanitise_file_name(name).replace('.', '_')


class Mkchdir:
    d = ""

    def __init__(self, d, sanitize=True):
        self.d = sanitise_folder_name(d) if sanitize else d

    def __enter__(self):
        try:
            os.mkdir(self.d)
        except OSError:
            pass
        os.chdir(self.d)

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir('..')


class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        if '%f' in datefmt:
            datefmt = datefmt.replace('%f', '%03d' % record.msecs)
        return logging.Formatter.formatTime(self, record, datefmt)


def init_cookie_jar(cookie_file=None, cookie_t=None, cookie_y=None, cookie_euconsent=None):
    cookie_jar = LWPCookieJar(cookie_file) if cookie_file else RequestsCookieJar()

    if cookie_file and os.path.exists(cookie_file):
        cookie_jar.load(ignore_discard=True)

    if args.cookie_t:
        cookie_jar.set_cookie(create_cookie('T', cookie_t))
    if cookie_y:
        cookie_jar.set_cookie(create_cookie('Y', cookie_y))
    if cookie_euconsent:
        cookie_jar.set_cookie(create_cookie('EuConsent', cookie_euconsent))

    if cookie_file:
        cookie_jar.save(ignore_discard=True)

    return cookie_jar


if __name__ == "__main__":
    p = argparse.ArgumentParser()

    pa = p.add_argument_group(title='Authentication Options')
    pa.add_argument('-ct', '--cookie_t', type=str,
                    help='T authentication cookie from yahoo.com')
    pa.add_argument('-cy', '--cookie_y', type=str,
                    help='Y authentication cookie from yahoo.com')
    pa.add_argument('-ce', '--cookie_e', type=str, default='',
                    help='Additional EuConsent cookie is required in EU')
    pa.add_argument('-cf', '--cookie-file', type=str,
                    help='File to store authentication cookies to. Cookies passed on the command line will overwrite '
                    'any already in the file.')

    po = p.add_argument_group(title='What to archive', description='By default, all the below.')
    po.add_argument('-e', '--email', action='store_true',
                    help='Only archive email and attachments (from email)')
    po.add_argument('-at', '--attachments', action='store_true',
                    help='Only archive attachments (from attachments list)')
    po.add_argument('-f', '--files', action='store_true',
                    help='Only archive files')
    po.add_argument('-i', '--photos', action='store_true',
                    help='Only archive photo galleries')
    po.add_argument('-d', '--database', action='store_true',
                    help='Only archive database')
    po.add_argument('-l', '--links', action='store_true',
                    help='Only archive links')
    po.add_argument('-c', '--calendar', action='store_true',
                    help='Only archive events')
    po.add_argument('-p', '--polls', action='store_true',
                    help='Only archive polls')
    po.add_argument('-a', '--about', action='store_true',
                    help='Only archive general info about the group')
    po.add_argument('-m', '--members', action='store_true',
                    help='Only archive members')

    pr = p.add_argument_group(title='Request Options')
    pr.add_argument('--user-agent', type=str,
                    help='Override the default user agent used to make requests')

    pc = p.add_argument_group(title='Message Range Options',
                              description='Options to specify which messages to download. Use of multiple options will '
                              'be combined. Note: These options will also try to fetch message IDs that may not exist '
                              'in the group.')
    pc.add_argument('--start', type=int,
                    help='Email message id to start from (specifying this will cause only specified message contents to'
                    ' be downloaded, and not message indexes). Default to 1, if end option provided.')
    pc.add_argument('--stop', type=int,
                    help='Email message id to stop at (inclusive), defaults to last message ID available, if start '
                    'option provided.')
    pc.add_argument('--ids', nargs='+', type=int,
                    help='Get email message by ID(s). Space separated, terminated by another flag or --')

    pf = p.add_argument_group(title='Output Options')
    pf.add_argument('-w', '--warc', action='store_true',
                    help='Output WARC file of raw network requests. [Requires warcio package installed]')

    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('--colour', '--color', action='store_true', help='Colour log output to terminal')
    p.add_argument('--delay', type=float, default=0.2, help='Minimum delay between requests (default 0.2s)')

    p.add_argument('group', type=str)

    args = p.parse_args()

    # Setup logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    log_format = {'fmt': '%(asctime)s %(levelname)s %(name)s %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S.%f %Z'}
    log_formatter = CustomFormatter(**log_format)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    if args.colour:
        try:
            import coloredlogs
        except ImportError as e:
            print("Coloured logging output requires the 'coloredlogs' package to be installed.")
            raise e
        coloredlogs.install(level=log_level, **log_format)
    else:
        log_stdout_handler = logging.StreamHandler(sys.stdout)
        log_stdout_handler.setLevel(log_level)
        log_stdout_handler.setFormatter(log_formatter)
        root_logger.addHandler(log_stdout_handler)

    cookie_jar = init_cookie_jar(args.cookie_file, args.cookie_t, args.cookie_y, args.cookie_e)

    headers = {}
    if args.user_agent:
        headers['User-Agent'] = args.user_agent

    yga = YahooGroupsAPI(args.group, cookie_jar, headers, min_delay=args.delay)

    if not (args.email or args.files or args.photos or args.database or args.links or args.calendar or args.about or
            args.polls or args.attachments or args.members):
        args.email = args.files = args.photos = args.database = args.links = args.calendar = args.about = \
            args.polls = args.attachments = args.members = True

    with Mkchdir(args.group, sanitize=False):
        log_file_handler = logging.FileHandler('archive.log')
        log_file_handler.setFormatter(log_formatter)
        root_logger.addHandler(log_file_handler)

        if args.warc:
            try:
                from warcio import WARCWriter
            except ImportError:
                logging.error('WARC output requires the warcio package to be installed.')
                exit(1)
            fhwarc = open('data.warc.gz', 'ab')
            warc_writer = WARCWriter(fhwarc)
            warcmeta = warc_writer.create_warcinfo_record(fhwarc.name, WARC_META_PARAMS)
            warc_writer.write_record(warcmeta)
            yga.set_warc_writer(warc_writer)

        if args.email:
            with Mkchdir('email'):
                archive_email(yga, message_subset=args.ids, start=args.start, stop=args.stop)
        if args.files:
            with Mkchdir('files'):
                archive_files(yga)
        if args.photos:
            with Mkchdir('photos'):
                archive_photos(yga)
        if args.database:
            with Mkchdir('databases'):
                archive_db(yga)
        if args.links:
            with Mkchdir('links'):
                archive_links(yga)
        if args.calendar:
            with Mkchdir('calendar'):
                archive_calendar(yga)
        if args.about:
            with Mkchdir('about'):
                archive_about(yga)
        if args.polls:
            with Mkchdir('polls'):
                archive_polls(yga)
        if args.attachments:
            with Mkchdir('attachments'):
                archive_attachments(yga)
        if args.members:
            with Mkchdir('members'):
                archive_members(yga)

        if args.warc:
            fhwarc.close()
