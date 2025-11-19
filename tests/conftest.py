def pytest_addoption(parser):
    parser.addoption("--proxy-url", action="store", default="example.com")
    parser.addoption("--test-url", action="store", default="example.com")
    parser.addoption("--count", action="store", default="10")




