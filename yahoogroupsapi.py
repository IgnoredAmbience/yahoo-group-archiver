import functools
import logging
import time
import requests


class YahooGroupsAPI:
    BASE_URI = "https://groups.yahoo.com/api"
    LOGIN_URI = "https://login.yahoo.com/"

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

    def __init__(self, group, cookie_t, cookie_y, cookie_euconsent):
        self.s = requests.Session()
        self.group = group
        jar = requests.cookies.RequestsCookieJar()
        jar.set('T', cookie_t)
        jar.set('Y', cookie_y)
        jar.set('EuConsent', cookie_euconsent)
        self.s.cookies = jar
        self.s.headers = {'Referer': self.BASE_URI}

    def __getattr__(self, name):
        """
        Easy, human-readable REST stub, eg:
           yga.messages(123, 'raw')
           yga.messages(count=50)
        """
        if name not in self.API_VERSIONS:
            raise AttributeError()
        return functools.partial(self.get_json, name)

    def login(self, user, password):
        data = {'login': user, 'passwd': password}
        self.s.post(self.LOGIN_URI, data=data, timeout=10)

        # On success, 302 redirect setting lots of cookies to 200 /config/verify
        # On fail, 302 redirect setting 1 cookie to 200 /m
        # For now check that we 'enough' cookies set.
        return len(self.s.cookies) > 2

    def get_file(self, url):
        r = self.s.get(url, verify=False)  # Needed to disable SSL verifying
        return r.content

    def get_file_nostatus(self, url):
        r = self.s.get(url)
        return r.content

    def download_file(self, url, f, **args):
        retries = 5
        while True:
            r = self.s.get(url, stream=True, verify=False, **args)
            if r.status_code == 400 and retries > 0:
                self.logger.info("Got 400 error for %s, will sleep and retry %d times", url, retries)
                retries -= 1
                time.sleep(5)
                continue
            r.raise_for_status()
            break
        for chunk in r.iter_content(chunk_size=4096):
            f.write(chunk)

    def get_json(self, target, *parts, **opts):
        """Get an arbitrary endpoint and parse as json"""

        uri_parts = [self.BASE_URI, self.API_VERSIONS[target], 'groups', self.group, target]
        uri_parts = uri_parts + map(str, parts)

        if target == 'HackGroupInfo':
            uri_parts[4] = ''

        uri = "/".join(uri_parts)

        r = self.s.get(uri, params=opts, allow_redirects=False, timeout=15)
        try:
            r.raise_for_status()
            if r.status_code != 200:
                raise requests.exceptions.HTTPError(response=r)
            return r.json()['ygData']
        except Exception as e:
            self.logger.debug("Exception raised on uri: %s", r.request.url)
            self.logger.debug(r.content)
            raise e
