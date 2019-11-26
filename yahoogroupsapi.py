# Warning: This module must be imported before any imports of the requests module.

from __future__ import unicode_literals
from contextlib import contextmanager
import functools
import logging
import os
import random
import time

try:
    from warcio.capture_http import capture_http
    warcio_failed = False
except ImportError as e:
    warcio_failed = e

import requests  # Must be imported after capture_http
from requests.exceptions import Timeout, ConnectionError

VERIFY_HTTPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yahoogroups_cert_chain.pem')


@contextmanager
def dummy_contextmanager(*kargs, **kwargs):
    yield


class YGAException(Exception):
    pass


class Unrecoverable(YGAException):
    """An error that can not be resolved by retrying the request."""
    pass


class AuthenticationError(Unrecoverable):
    pass


class NotAuthenticated(AuthenticationError):
    """307, with Yahoo errorCode 1101, user is not logged in and attempting to read content requiring authentication."""
    pass


class Unauthorized(AuthenticationError):
    """401, with Yahoo errorCode 1103, user does not have permissions to access this resource."""
    pass


class NotFound(Unrecoverable):
    pass


class Recoverable(YGAException):
    pass


class BadSize(YGAException):
    """The filesize is between 60 and 68 bytes, which could be in error"""
    pass


class YahooGroupsAPI:
    BASE_URI = "https://groups.yahoo.com/api"

    API_VERSIONS = {
            'HackGroupInfo': 'v1',  # In reality, this will get the root endpoint
            'messages': 'v1',
            'files': 'v2',
            'albums': 'v2',         # v3 is available, but changes where photos are located in json
            'database': 'v1',
            'links': 'v1',
            'statistics': 'v1',
            'polls': 'v1',
            'attachments': 'v1',
            'members': 'v1'
            }

    logger = logging.getLogger(name="YahooGroupsAPI")

    s = None
    ww = None
    http_context = dummy_contextmanager

    def __init__(self, group, cookie_jar=None, headers={}, min_delay=0, retries=10):
        self.s = requests.Session()
        self.group = group
        self.min_delay = min_delay
        self.retries = retries

        if cookie_jar:
            self.s.cookies = cookie_jar
        self.s.headers = {'Referer': self.BASE_URI}
        self.s.headers.update(headers)

    def set_warc_writer(self, ww):
        if ww is not None and warcio_failed:
            self.logger.fatal("Attempting to log to warc, but warcio failed to import.")
            raise warcio_failed
        self.ww = ww
        self.http_context = capture_http

    def __getattr__(self, name):
        """ Return an API stub function for the API endpoint called name.

        Examples:
           yga.messages(123, 'raw') -> yga.get_json('messages')(123, 'raw') -> calls API endpoint '/messages/123/raw'
           yga.messages(count=50) -> yga.get_json('messages')(count=50) -> calls API endpoint '/messages?count=50'
        """
        self.API_VERSIONS[name]  # Tests that name is defined, and raises an AttributeError if not
        return functools.partial(self.get_json, name)

    def backoff_time(self, attempt):
        """Calculate backoff time from minimum delay and attempt number.
           Currently no good reason for choice of backoff, except not to increase too rapidly."""
        return max(self.min_delay, random.uniform(0, attempt))

    def download_file(self, url, f=None, **args):
        with self.http_context(self.ww):
            time.sleep(self.min_delay)

            for attempt in range(self.retries):
                r = self.s.get(url, verify=VERIFY_HTTPS, **args)
                if r.status_code == 400 or r.status_code == 500:
                    if r.status_code == 400 and 'malware' in r.text:
                        self.logger.warning("Got 400 error indicating malware for %s, skipping", url)
                        break
                    else:
                        self.logger.info("Got %d error for %s, will sleep and retry", r.status_code, url)
                        if attempt < self.retries-1:
                            delay = self.backoff_time(attempt)
                            self.logger.info("Attempt %d, delaying for %.2f seconds", attempt+1, delay)
                            time.sleep(delay)
                            continue
                        self.logger.warning("Giving up, too many failed attempts at downloading %s", url)
                elif r.status_code != 200:
                    self.logger.error("Unknown %d error for %s, giving up on this download", r.status_code, url)
                elif len(r.content) in range(60, 69):
                    self.logger.info("Got potentially invalid size of %d for %s, will sleep and retry", len(r.content), url)
                    if attempt < self.retries-1:
                        delay = self.backoff_time(attempt)
                        self.logger.info("Attempt %d, delaying for %.2f seconds", attempt+1, delay)
                        time.sleep(delay)
                        continue
                    self.logger.warning("Giving up, too many potentially failed attempts at downloading %s", url)
                r.raise_for_status()
                break

            if f is None:
                return r.content
            else:
                f.write(r.content)

    def get_json(self, target, *parts, **opts):
        """Get an arbitrary endpoint and parse as json"""
        with self.http_context(self.ww):
            uri_parts = [self.BASE_URI, self.API_VERSIONS[target], 'groups', self.group, target]
            uri_parts = uri_parts + list(map(str, parts))

            if target == 'HackGroupInfo':
                uri_parts[4] = ''

            uri = "/".join(uri_parts)
            time.sleep(self.min_delay)

            for attempt in range(self.retries):
                try:
                    r = self.s.get(uri, params=opts, verify=VERIFY_HTTPS, allow_redirects=False, timeout=15)

                    code = r.status_code
                    if code == 307:
                        raise NotAuthenticated()
                    elif code == 401 or code == 403:
                        raise Unauthorized()
                    elif code == 404:
                        raise NotFound()
                    elif len(r.content) in range(60, 69):
                        raise BadSize()
                    elif code != 200:
                        # TODO: Test ygError response?
                        raise Recoverable()

                    return r.json()['ygData']
                except (ConnectionError, Timeout, Recoverable, BadSize) as e:
                    self.logger.info("API query failed for '%s': %s", uri, e)
                    self.logger.debug("Exception detail:", exc_info=e)

                    if attempt < self.retries - 1:
                        delay = self.backoff_time(attempt)
                        self.logger.info("Attempt %d/%d failed, delaying for %.2f seconds", attempt+1, self.retries, delay)
                        time.sleep(delay)
                        continue
                    else:
                        raise
