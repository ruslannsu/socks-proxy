import pytest 
import requests
from concurrent.futures import ThreadPoolExecutor

@pytest.fixture
def proxy_url(pytestconfig):
    return pytestconfig.getoption('--proxy-url')

@pytest.fixture
def test_file_url(pytestconfig):
    return pytestconfig.getoption('--test-url')

@pytest.fixture
def test_count(pytestconfig):
    return pytestconfig.getoption('--count')

def get_test_file(args):
    url, proxies = args
    return requests.get(url=url, proxies=proxies)

def test_conc(proxy_url, test_file_url, test_count):
    base_file = requests.get(url=test_file_url)
    proxies = {'http': proxy_url, 'https': proxy_url}

    for i in range(int(test_count)):
        assert base_file.content == get_test_file((test_file_url, proxies)).content
    

        



















