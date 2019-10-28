from yahoogroupsapi import YahooGroupsAPI
import pytest
import responses
from requests.cookies import RequestsCookieJar
import sys
if (sys.version_info < (3, 0)):
    from Cookie import SimpleCookie
else:
    from http.cookies import SimpleCookie

from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import BufferWARCWriter


@pytest.fixture
def yahoo_response():
    with responses.RequestsMock() as rsps:
        def add_yahoo_reponse(endpoint, ygData={}, ygPerms={}, method=responses.GET, *args, **kwargs):
            rsps.add(method=method, url='https://groups.yahoo.com/api/%s' % endpoint,
                     json={'ygPerms': ygPerms, 'ygData': ygData}, *args, **kwargs)
            return rsps

        yield add_yahoo_reponse

@pytest.fixture
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
    yga.get_json('HackGroupInfo')

    expected = [(url, 'response'), (url, 'request')]
    actual = [(record.rec_headers['WARC-Target-URI'], record.rec_type)
              for record in ArchiveIterator(writer.get_stream())]
    assert expected == actual

def test_correct_ua(yahoo_response):
    r = yahoo_response('v1/groups/groupname/')
    yga = YahooGroupsAPI('groupname', headers={'User-Agent': 'test'})
    yga.HackGroupInfo()
    assert r.calls[0].request.headers['user-agent'] == 'test'
