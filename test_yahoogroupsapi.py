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
def response():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def cookies():
    cookies = RequestsCookieJar()
    cookies.set('T', 't_cookie')
    cookies.set('Y', 'y_cookie')
    cookies.set('EuConsent', 'eu_cookie')
    yield cookies


def test_get_json(response, cookies):
    response.add(responses.GET, 'https://groups.yahoo.com/api/v2/groups/groupname/files/a/2?param1=c&param2=4',
                 json={'ygData': {'result': 'returned data'}})

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
