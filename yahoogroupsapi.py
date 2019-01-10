import requests
from HTMLParser import HTMLParser
import json
import functools

class YahooGroupsAPI:
    BASE_URI="https://groups.yahoo.com/api"
    LOGIN_URI="https://login.yahoo.com/"

    API_VERSIONS={
            'messages': 'v1',
            'files': 'v2',
            'albums': 'v2', # v3 is available, but changes where photos are located in json
            'database': 'v1'
            }

    s = None

    def __init__(self, group, cookie_t, cookie_y):
        self.s = requests.Session()
        self.group = group
        jar = requests.cookies.RequestsCookieJar()
        jar.set('T', cookie_t)
        jar.set('Y', cookie_y)
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
        r = self.s.post(self.LOGIN_URI, data=data, timeout=10)

        # On success, 302 redirect setting lots of cookies to 200 /config/verify
        # On fail, 302 redirect setting 1 cookie to 200 /m
        # For now check that we 'enough' cookies set.
        return len(self.s.cookies) > 2

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
        uri_parts = [self.BASE_URI, self.API_VERSIONS[target], 'groups', self.group, target]
        uri_parts = uri_parts + map(str, parts)
        uri = "/".join(uri_parts)

        r = self.s.get(uri, params=opts, allow_redirects=False, timeout=10)
        try:
            r.raise_for_status()
            if r.status_code != 200:
                raise requests.exceptions.HTTPError(response=r)
            return r.json()['ygData']
        except Exception as e:
            print "Exception raised on uri: " + r.request.url
            print r.content
            raise e

