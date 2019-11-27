import yahoogroupsapi  # Must be imported first
from yahoogroupsapi import YahooGroupsAPI

import responses
import sys
from pytest import fixture, raises
from requests.cookies import RequestsCookieJar
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import BufferWARCWriter

if (sys.version_info < (3, 0)):
    from Cookie import SimpleCookie
else:
    from http.cookies import SimpleCookie

YGPERMS_NONE = {"resourceCapabilityList": [
    {"resourceType": "GROUP", "capabilities": []}, {"resourceType": "PHOTO", "capabilities": []},
    {"resourceType": "FILE", "capabilities": []}, {"resourceType": "MEMBER", "capabilities": []},
    {"resourceType": "LINK", "capabilities": []}, {"resourceType": "CALENDAR", "capabilities": []},
    {"resourceType": "DATABASE", "capabilities": []}, {"resourceType": "POLL", "capabilities": []},
    {"resourceType": "MESSAGE", "capabilities": []}, {"resourceType": "PENDING_MESSAGE", "capabilities": []},
    {"resourceType": "ATTACHMENTS", "capabilities": []}, {"resourceType": "PHOTOMATIC_ALBUMS", "capabilities": []},
    {"resourceType": "MEMBERSHIP_TYPE", "capabilities": []}, {"resourceType": "POST", "capabilities": []},
    {"resourceType": "PIN", "capabilities": []}
    ], "groupUrl": "groups.yahoo.com", "intlCode": "us"}


@fixture
def yahoo_response():
    with responses.RequestsMock() as rsps:
        def add_yahoo_reponse(endpoint, ygData=None, ygPerms={}, ygError=None, method=responses.GET, status=200, **kwargs):
            if status >= 300 and status < 400:
                json = None
            else:
                json = {'ygPerms': ygPerms}
                if ygData is not None:
                    json['ygData'] = ygData
                elif ygError is not None:
                    json['ygError'] = ygError

            rsps.add(method=method, url='https://groups.yahoo.com/api/%s' % endpoint, json=json, status=status, **kwargs)
            return rsps

        yield add_yahoo_reponse


@fixture
def cookies():
    cookies = RequestsCookieJar()
    cookies.set('T', 't_cookie')
    cookies.set('Y', 'y_cookie')
    cookies.set('EuConsent', 'eu_cookie')
    yield cookies


def test_get_json(yahoo_response, cookies):
    response = yahoo_response('v2/groups/groupname/files/a/2?param1=c&param2=4', {'result': 'returned data'})

    yga = YahooGroupsAPI('groupname', cookies)
    json = yga.get_json('files', 'a', 2, param1='c', param2=4)

    request = response.calls[0].request
    request_cookies = SimpleCookie()
    request_cookies.load(request.headers['Cookie'])
    assert dict(cookies) == {k: v.value for k, v in request_cookies.items()}

    assert json == {'result': 'returned data'}


def test_warc_enabled():
    # Note that this does not use the responses mocking framework, as it conflicts with the warc captures.
    # This makes a real request to Yahoo, so might fail.
    url = 'https://groups.yahoo.com/api/v1/groups/test/'

    yga = YahooGroupsAPI('test')
    writer = BufferWARCWriter(gzip=False)
    yga.set_warc_writer(writer)
    yga.HackGroupInfo()

    expected = [(url, 'response'), (url, 'request')]
    actual = [(record.rec_headers['WARC-Target-URI'], record.rec_type)
              for record in ArchiveIterator(writer.get_stream())]
    assert expected == actual


def test_correct_ua(yahoo_response):
    r = yahoo_response('v1/groups/groupname/', {})
    yga = YahooGroupsAPI('groupname', headers={'User-Agent': 'test'})
    yga.HackGroupInfo()
    assert r.calls[0].request.headers['user-agent'] == 'test'


def test_unauthorized_error(yahoo_response):
    r = yahoo_response('v1/groups/groupname/',
                       ygError={"hostname": "gapi17.grp.bf1.yahoo.com", "httpStatus": 401,
                                "errorMessage": "User does not have READ permission for GROUP. Mess...", "errorCode": 1103,
                                "sid": "SID:YHOO:groups.yahoo.com:00000000000000000000000000000000:0"},
                       ygPerms=YGPERMS_NONE, status=401)
    yga = YahooGroupsAPI('groupname')
    with raises(yahoogroupsapi.Unauthorized):
        yga.HackGroupInfo()
    assert len(r.calls) == 1


def test_not_authenticated_error(yahoo_response):
    r = yahoo_response('v1/groups/groupname/', status=307)
    yga = YahooGroupsAPI('groupname')
    with raises(yahoogroupsapi.Recoverable):    # Temporary fix, replaced: yahoogroupsapi.NotAuthenticated
        yga.HackGroupInfo()
    assert len(r.calls) == 15


def test_one_retry(yahoo_response):
    result = {'ok': 'on second try'}
    r = yahoo_response('v1/groups/groupname/', ygError={}, status=500)
    r = yahoo_response('v1/groups/groupname/', result)
    yga = YahooGroupsAPI('groupname')
    json = yga.HackGroupInfo()

    assert len(r.calls) == 2
    assert json == result


def test_fifteen_retries(yahoo_response):
    r = yahoo_response('v1/groups/groupname/', ygError={}, status=500)
    yga = YahooGroupsAPI('groupname')
    with raises(yahoogroupsapi.Recoverable):
        yga.HackGroupInfo()

    assert len(r.calls) == 15
