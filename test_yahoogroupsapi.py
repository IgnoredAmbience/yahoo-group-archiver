from yahoogroupsapi import YahooGroupsAPI
import Cookie
import pytest
import responses

from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import BufferWARCWriter


@pytest.fixture
def response():
    with responses.RequestsMock() as rsps:
        yield rsps


def test_get_json(response):
    response.add(responses.GET, 'https://groups.yahoo.com/api/v2/groups/groupname/files/a/2?param1=c&param2=4',
                 json={'ygData': {'result': 'returned data'}})

    t_cookie = 't_cookie'
    y_cookie = 'y_cookie'
    eu_cookie = 'eu_cookie'

    yga = YahooGroupsAPI('groupname', t_cookie, y_cookie, eu_cookie)
    json = yga.get_json('files', 'a', 2, param1='c', param2=4)

    request = response.calls[0].request
    cookies = Cookie.SimpleCookie()
    cookies.load(request.headers['Cookie'])
    assert cookies['T'].value == t_cookie
    assert cookies['Y'].value == y_cookie
    assert cookies['EuConsent'].value == eu_cookie
    assert json == {'result': 'returned data'}


def test_warc_enabled():
    # Note that this does not use the responses mocking framework, as it conflicts with the warc captures.
    # This makes a real request to Yahoo, so might fail.
    url = 'https://groups.yahoo.com/api/v1/groups/test/'

    yga = YahooGroupsAPI('test', '', '', '')
    writer = BufferWARCWriter(gzip=False)
    yga.set_warc_writer(writer)
    yga.get_json('HackGroupInfo')

    expected = [(url, 'response'), (url, 'request')]
    actual = [(record.rec_headers['WARC-Target-URI'], record.rec_type)
              for record in ArchiveIterator(writer.get_stream())]
    assert expected == actual
