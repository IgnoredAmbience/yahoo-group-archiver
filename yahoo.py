#!/usr/bin/env python
import requests
import json
import functools

import argparse
import getpass

class YahooGroupsAPI:
    BASE_URI="https://groups.yahoo.com/api/v1/groups/"
    loggedin = False
    s = None

    def __init__(self, group):
        self.s = requests.Session()
        self.group = group

    def __getattr__(self, name):
        return functools.partial(self.get, name)

    def login(self, user, password):
        r = self.s.post("https://login.yahoo.com/config/login", data={"login":user, "passwd":password})
        if r.status_code != requests.codes.ok:
            r.raise_for_status()
            raise HTTPError(r.status_code, r.text)

    def get(self, target, *parts, **opts):
        uri = "/".join((self.BASE_URI, self.group, target) + parts)
        r = self.s.get(uri, data=opts)
        r.raise_for_status()
        print r.text
        return r.json()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument('-u', '--username', type=str, dest='username')
    p.add_argument('-p', '--password', type=str, dest='password')
    p.add_argument('group', type=str)

    args = p.parse_args()

    yga = YahooGroupsAPI(args.group)
    if args.username:
        password = args.password or getpass.getpass()
        yga.login(args.username, password)

    print yga.messages()

