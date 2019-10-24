#!/usr/bin/env python2
import argparse
import datetime
from yahoogroupsapi import YahooGroupsAPI

import json
import logging
import math
import os
import requests.exceptions
import sys
import time
import urllib
from cookielib import LWPCookieJar
from HTMLParser import HTMLParser
from os.path import basename
from requests.cookies import RequestsCookieJar, create_cookie

# number of seconds to wait before trying again
HOLDOFF = 10

# max tries
TRIES = 10

hp = HTMLParser()


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


def archive_email(yga, save=True, html=True):
    logger = logging.getLogger('archive_email')
    try:
        msg_json = yga.messages()
    except requests.exceptions.HTTPError as err:
        logger.error("Couldn't download message; %s", err.message)
        return

    count = msg_json['totalRecords']

    msg_json = yga.messages(count=count)
    logger.info("Group has %s messages, got %s", count, msg_json['numRecords'])

    for message in msg_json['messages']:
        id = message['messageId']

        logger.info("Fetching raw message #%d of %d", id, count)
        for i in range(TRIES):
            try:
                raw_json = yga.messages(id, 'raw')
                break
            except requests.exceptions.ReadTimeout:
                logger.error("Read timeout for raw message %d of %d, retrying", id, count)
                time.sleep(HOLDOFF)
            except requests.exceptions.HTTPError as err:
                logger.error("Raw grab failed for message %d of %d", id, count)
                break
        if html:
            logger.info("* Fetching html message #%d of %d", id, count)
            for i in range(TRIES):
                try:
                    html_json = yga.messages(id)
                    break
                except requests.exceptions.ReadTimeout:
                    logger.error("Read timeout for html message %d of %d, retrying", id, count)
                    time.sleep(HOLDOFF)
                except requests.exceptions.HTTPError:
                    logger.error("HTML grab failed for message %d of %d", id, count)
                    break

        if save and message['hasAttachments']:
            if 'attachments' not in message:
                logger.warning("Yahoo says this message (%d of %d) has attachments, but I can't find any!", id, count)
            else:
                atts = {}
                for attach in message['attachments']:
                    logger.info("Fetching attachment '%s'", attach['filename'])
                    if 'link' in attach:
                        # try and download the attachment
                        # (sometimes yahoo doesn't keep them)
                        for i in range(TRIES):
                            try:
                                atts[attach['filename']] = yga.download_file(attach['link'])
                                break
                            except requests.exceptions.HTTPError as err:
                                logger.error("Can't download attachment, try %d: %s", i, err)
                                time.sleep(HOLDOFF)

                    elif 'photoInfo' in attach:
                        # keep retrying until we find the largest image size we can download
                        # (sometimes yahoo doesn't keep the originals)
                        exclude = []
                        ok = False
                        while not ok:
                            # find best photoinfo (largest size)
                            photoinfo = get_best_photoinfo(attach['photoInfo'], exclude)

                            if photoinfo is None:
                                logger.error("Can't find a viable copy of this photo")
                                break

                            # try and download it
                            for i in range(TRIES):
                                try:
                                    atts[attach['filename']] = yga.download_file(photoinfo['displayURL'])
                                    ok = True
                                    break
                                except requests.exceptions.HTTPError as err:
                                    # yahoo says no. exclude this size and try for another.
                                    logger.error("Can't download '%s' variant, try %d: %s", photoinfo['photoType'], i, err)
                                    time.sleep(HOLDOFF)
                                    # exclude.append(photoinfo['photoType'])

                        # if we failed, try the next attachment
                        if not ok:
                            continue

                        if save:
                            fname = "%s-%s" % (id, basename(attach['filename']))
                            with file(fname, 'wb') as f:
                                f.write(atts[attach['filename']])

        with file("%s_raw.json" % (id,), 'w') as f:
            f.write(json.dumps(raw_json, indent=4))

        if html:
            with file("%s.json" % (id,), 'w') as f:
                f.write(json.dumps(html_json, indent=4))


def process_single_attachment(yga, attach):
    logger = logging.getLogger(name="process_single_attachment")
    for frec in attach['files']:
        logger.info("Fetching attachment '%s'", frec['filename'])
        if 'link' in frec:
            # try and download the attachment
            # (sometimes yahoo doesn't keep them)
            for i in range(TRIES):
                try:
                    att = yga.download_file(frec['link'])
                    break
                except requests.exceptions.HTTPError as err:
                    logger.error("Can't download attachment, try %d: %s", i, err)
                    time.sleep(HOLDOFF)

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
                for i in range(TRIES):
                    try:
                        att = yga.download_file(photoinfo['displayURL'])
                        ok = True
                        break
                    except requests.exceptions.HTTPError as err:
                        # yahoo says no. exclude this size and try for another.
                        logger.error("ERROR downloading '%s' variant, try %d: %s", photoinfo['photoType'], i, err)
                        time.sleep(HOLDOFF)
                        # exclude.append(photoinfo['photoType'])

            # if we failed, try the next attachment
            if not ok:
                return None

        fname = "%s-%s" % (frec['fileId'], basename(frec['filename']))
        with file(fname, 'wb') as f:
            f.write(att)


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

    with open('fileinfo.json', 'w') as f:
        f.write(json.dumps(file_json['dirEntries'], indent=4))

    n = 0
    sz = len(file_json['dirEntries'])
    for path in file_json['dirEntries']:
        n += 1
        if path['type'] == 0:
            # Regular file
            name = hp.unescape(path['fileName']).replace("/", "_")
            logger.info("Fetching file '%s' (%d/%d)", name, n, sz)
            with open(basename(name), 'wb') as f:
                yga.download_file(path['downloadURL'], f)

        elif path['type'] == 1:
            # Directory
            logger.info("Fetching directory '%s' (%d/%d)", path['fileName'], n, sz)
            with Mkchdir(basename(path['fileName']).replace('.', '')):
                pathURI = urllib.unquote(path['pathURI'])
                archive_files(yga, subdir=pathURI)


def archive_attachments(yga):
    logger = logging.getLogger(name="archive_attachments")
    try:
        attachments_json = yga.attachments()
    except Exception:
        logger.error("Couldn't access Attachments functionality for this group")
        return

    with open('allattachmentinfo.json', 'w') as f:
        f.write(json.dumps(attachments_json['attachments'], indent=4))

    n = 0
    for a in attachments_json['attachments']:
        n += 1
        with Mkchdir(str(a['attachmentId'])):
            try:
                a_json = yga.attachments(a['attachmentId'])
            except Exception:
                logger.error("Attachment id %d inaccessible.", a['attachmentId'])
                continue
            with open('attachmentinfo.json', 'w') as f:
                f.write(json.dumps(a_json, indent=4))
                process_single_attachment(yga, a_json)


def archive_photos(yga):
    logger = logging.getLogger(name="archive_photos")
    try:
        nb_albums = yga.albums(count=5)['total'] + 1
    except Exception:
        logger.error("Couldn't access Photos functionality for this group")
        return
    albums = yga.albums(count=nb_albums)
    n = 0

    with open('albums.json', 'w') as f:
        f.write(json.dumps(albums['albums'], indent=4))

    for a in albums['albums']:
        n += 1
        name = hp.unescape(a['albumName']).replace("/", "_")
        # Yahoo has an off-by-one error in the album count...
        logger.info("Fetching album '%s' (%d/%d)", name, n, albums['total'] - 1)

        with Mkchdir(basename(name).replace('.', '')):
            photos = yga.albums(a['albumId'])
            pages = photos['total'] / 100 + 1
            p = 0

            for page in range(pages):
                photos = yga.albums(a['albumId'], start=page*100, count=100)
                with open('photos-%d.json' % page, 'w') as f:
                    f.write(json.dumps(photos['photos'], indent=4))

                for photo in photos['photos']:
                    p += 1
                    pname = hp.unescape(photo['photoName']).replace("/", "_")
                    logger.info("Fetching photo '%s' (%d/%d)", pname, p, photos['total'])

                    photoinfo = get_best_photoinfo(photo['photoInfo'])
                    fname = "%d-%s.jpg" % (photo['photoId'], basename(pname))
                    with open(fname, 'wb') as f:
                        for i in range(TRIES):
                            try:
                                yga.download_file(photoinfo['displayURL'], f)
                                break
                            except requests.exceptions.HTTPError as err:
                                logger.error("HTTP error (sleeping before retry, try %d: %s", i, err)
                                time.sleep(HOLDOFF)


def archive_db(yga):
    logger = logging.getLogger(name="archive_db")
    for i in range(TRIES):
        try:
            json = yga.database()
            break
        except requests.exceptions.HTTPError as err:
            json = None
            if err.response.status_code == 403 or err.response.status_code == 401:
                # 401 or 403 error means Permission Denied. Retrying won't help.
                break
            logger.error("HTTP error (sleeping before retry, try %d: %s", i, err)
            time.sleep(HOLDOFF)

    if json is None:
        logger.error("ERROR: Couldn't access Database functionality for this group")
        return

    n = 0
    nts = len(json['tables'])
    for table in json['tables']:
        n += 1
        logger.info("Downloading database table '%s' (%d/%d)", table['name'], n, nts)

        name = basename(table['name']) + '.csv'
        uri = "https://groups.yahoo.com/neo/groups/%s/database/%s/records/export?format=csv" % (yga.group, table['tableId'])
        with open(name, 'w') as f:
            yga.download_file(uri, f)


def archive_links(yga, subdir=''):
    logger = logging.getLogger(name="archive_links")

    try:
        links = yga.links(linkdir=subdir)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            logger.warn("User doesn't have permission to access Links in this group.")
            return
        else:
            raise e

    with open('links.json', 'w') as f:
        f.write(json.dumps(links, indent=4))
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
        logger.error("Attempt to get wssid returned HTTP 200, which is unexpected!") # we should never hit this
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

        for i in range(TRIES):
            try:
                logger.info("Trying to get events between %s and %s", jsonStart, jsonEnd)
                calContentRaw = yga.download_file(calURL)
                break
            except requests.exceptions.HTTPError as err:
                logger.error("HTTP error (sleeping before retry, try %d: %s", i, err)
                time.sleep(HOLDOFF)

        calContent = json.loads(calContentRaw)
        if calContent['events']['count'] > 0:
            filename = jsonStart + "-" + jsonEnd + ".json"
            with open(filename, 'wb') as f:
                logger.info("Got %d event(s)", calContent['events']['count'])
                f.write(json.dumps(calContent, indent=4))

        archiveDate += datetime.timedelta(days=1000)


def archive_about(yga):
    logger = logging.getLogger(name="archive_about")
    groupinfo = yga.HackGroupInfo()

    with open('about.json', 'wb') as f:
        f.write(json.dumps(groupinfo, indent=4))

    statistics = yga.statistics()

    with open('statistics.json', 'wb') as f:
        f.write(json.dumps(statistics, indent=4))

    # Check if we really have a photo in the group description
    if ('photoInfo' in statistics['groupHomePage'] and statistics['groupHomePage']['photoInfo']):
        exclude = []

        # find best photoinfo (largest size)
        photoinfo = get_best_photoinfo(statistics['groupHomePage']['photoInfo'], exclude)

        if photoinfo is not None:
            fname = 'GroupPhoto-%s' % basename(photoinfo['displayURL']).split('?')[0]
            logger.info("Downloading the photo in group description as %s", fname)
            for i in range(TRIES):
                try:
                    with open(fname, 'wb') as f:
                        yga.download_file(photoinfo['displayURL'], f)
                        break
                except requests.exceptions.HTTPError as err:
                    logger.error("HTTP error (sleeping before retry, try %d: %s", i, err)
                    time.sleep(HOLDOFF)

    if statistics['groupCoverPhoto']['hasCoverImage']:
        exclude = []

        # find best photoinfo (largest size)
        photoinfo = get_best_photoinfo(statistics['groupCoverPhoto']['photoInfo'], exclude)

        if photoinfo is not None:
            fname = 'GroupCover-%s' % basename(photoinfo['displayURL']).split('?')[0]
            logger.info("Downloading the group cover as %s", fname)
            for i in range(TRIES):
                try:
                    with open(fname, 'wb') as f:
                        yga.download_file(photoinfo['displayURL'], f)
                        break
                except requests.exceptions.HTTPError as err:
                    logger.error("HTTP error (sleeping before retry, try %d: %s", i, err)
                    time.sleep(HOLDOFF)


def archive_polls(yga):
    logger = logging.getLogger(name="archive_polls")
    try:
        pollsList = yga.polls(count=100, sort='DESC')
    except Exception:
        logger.error("ERROR: Couldn't access Polls functionality for this group")
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

    n = 1
    for p in pollsList:
        logger.info("Downloading poll %d [%d/%d]", p['surveyId'], n, totalPolls)
        pollInfo = yga.polls(p['surveyId'])
        fname = '%s-%s.json' % (n, p['surveyId'])

        with open(fname, 'wb') as f:
            f.write(json.dumps(pollInfo, indent=4))
        n += 1


def archive_members(yga):
    logger = logging.getLogger(name="archive_members")
    for i in range(TRIES):
        try:
            confirmed_json = yga.members('confirmed')
            break
        except requests.exceptions.HTTPError as err:
            confirmed_json = None
            if err.response.status_code == 403 or err.response.status_code == 401:
                # 401 or 403 error means Permission Denied. Retrying won't help.
                logger.error("Permission denied to access members.")
                return
            logger.error("HTTP error (sleeping before retry, try %d: %s", i, err)
            time.sleep(HOLDOFF)
    n_members = confirmed_json['total']
    # we can dump 100 member records at a time
    all_members = []
    for i in range(int(math.ceil(n_members))/100 + 1):
        confirmed_json = yga.members('confirmed', start=100*i, count=100)
        all_members = all_members + confirmed_json['members']
        with open('memberinfo_%d.json' % i, 'w') as f:
            f.write(json.dumps(confirmed_json, indent=4))
    all_json_data = {"total": n_members, "members": all_members}
    with open('allmemberinfo.json', 'w') as f:
        f.write(json.dumps(all_json_data, indent=4))
    logger.info("Saved members: Expected: %d, Actual: %d", n_members, len(all_members))


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
    # Setup logging
    log_formatter = logging.Formatter(
            fmt='%(asctime)s %(msecs)03d %(levelname)s:%(name)s %(message)s',
            datefmt="%Y-%m-%d %H:%M:%S %Z"
            )
    log_stdout_handler = logging.StreamHandler(sys.stdout)
    log_stdout_handler.setFormatter(log_formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # This level gets dropped for stdout once we've got args parsed
    root_logger.addHandler(log_stdout_handler)

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

    pe = p.add_argument_group(title='Email Options')
    pe.add_argument('-s', '--no-save', action='store_true',
                    help="Don't save email attachments as individual files")
    pe.add_argument('--html', action='store_false',
                    help="Don't save the non-raw version of message")

    pf = p.add_argument_group(title='Output Options')
    pf.add_argument('-w', '--warc', action='store_true',
                    help='Output WARC file of raw network requests. [Requires warcio package installed]')

    p.add_argument('-v', '--verbose', action='store_true')

    p.add_argument('group', type=str)

    args = p.parse_args()

    if not args.verbose:
        log_stdout_handler.setLevel(logging.INFO)

    cookie_jar = init_cookie_jar(args.cookie_file, args.cookie_t, args.cookie_y, args.cookie_e)
    yga = YahooGroupsAPI(args.group, cookie_jar)

    if not (args.email or args.files or args.photos or args.database or args.links or args.calendar or args.about or
            args.polls or args.attachments or args.members):
        args.email = args.files = args.photos = args.database = args.links = args.calendar = args.about = \
            args.polls = args.attachments = args.members = True

    with Mkchdir(args.group):
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
            yga.set_warc_writer(warc_writer)

        if args.email:
            with Mkchdir('email'):
                archive_email(yga, save=(not args.no_save), html=args.html)
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
