import asyncio
import functools
import logging
import random
import re
from abc import ABCMeta, abstractmethod
from subprocess import TimeoutExpired
from urllib.parse import urlparse

import aiohttp
import aiosocks
import stem
from aiosocks.connector import SocksConnector
from lxml import html
from stem import control, CircStatus
from stem import process

from main_assistant.utils import run_async, weighed_choice, delayed_ensure_future, xpath_select, convert

logger = logging.getLogger(__name__)

RETRIES = 3
RETRY_BACKOFF = 10.0
REQUEST_TIMEOUT = 30.0
FAIL_EXCEPTION_TYPES = (
    asyncio.TimeoutError, aiosocks.errors.SocksError, aiohttp.errors.ClientError, aiohttp.errors.DisconnectedError,
    ConnectionResetError, aiohttp.ProxyConnectionError, aiohttp.HttpProxyError, aiohttp.errors.ContentEncodingError,
    aiohttp.errors.TransferEncodingError
)


class ProxySource(metaclass=ABCMeta):
    @abstractmethod
    async def getProxies(cls):
        raise NotImplementedError()


class ProxyListsProxies(ProxySource):
    URL = 'http://www.proxylists.net/'
    _RE_PATTERN = r'''
    ((?:\d{1,3}\.){3}(?:\d{1,3}):\d+)
    '''

    def __init__(self, web):
        self.web = web

    async def getProxies(self):
        resp = await self.web.get(self.URL)
        ret = set()
        for match in re.finditer(self._RE_PATTERN, str(resp.content), re.VERBOSE):
            address = 'http://{}/'.format(match.group(1))
            ret.add(address)
        return ret


class SpysRuProxies(ProxySource):
    URL = 'http://spys.ru/en/anonymous-proxy-list/'
    _ANONYMOUS = False
    _MIN_SPEED = 5
    _XF4_TO_PORT_MAP = {'1': '3128',
                        '2': '8080',
                        '3': '80'}

    def __init__(self, web):
        self.web = web

    async def getProxies(self):
        ret = set()
        # Experimental. Proxy list blocks by IP
        for xf4 in self._XF4_TO_PORT_MAP.keys():
            data = {
                'xpp': '3',
                'xf1': '1' if self._ANONYMOUS else '0',
                'xf2': '0',
                'xf4': xf4}
            resp = await self.web.get(self.URL)
            tree = html.fromstring(resp.content)
            rows = tree.xpath('//table[count(./tr)>20]/tr')
            for i in range(3, len(rows) - 1):
                row = rows[i]
                tds = row.xpath('./td')
                speed = int(xpath_select(tds[6], './font/table/@width'))
                if speed < self._MIN_SPEED:
                    continue
                ip = re.search(r'\s((?:\d{1,3}\.){3}\d{1,3})', tds[0].text_content()).group(1)
                address = 'http://{}:{}/'.format(ip, self._XF4_TO_PORT_MAP[xf4])
                ret.add(address)
        return ret


class GatherProxyProxies(ProxySource):
    URL = 'http://www.gatherproxy.com/'
    _ANONYMOUS = False
    # _MAX_RESPONSE_TIME = 10000
    _RE_PATTERN = r'''
    "PROXY_IP":"((?:\d{1,3}\.){3}(?:\d{1,3}))"
    .*"PROXY_PORT":"([\dABCDEF]+)"
    .*"PROXY_TIME":"(\d+)"
    .*?"PROXY_TYPE":"(\w+)"
    '''

    def __init__(self, web):
        self.web = web

    async def getProxies(self):
        resp = await self.web.get(self.URL)
        ret = set()
        for match in re.finditer(self._RE_PATTERN, str(resp.content), re.VERBOSE):
            type = match.group(4)
            if self._ANONYMOUS and not (type == 'Anonymous' or type == 'Elite'):
                continue
            # resp_time = int(match.group(3))
            # if resp_time > self._MAX_RESPONSE_TIME:
            #     continue
            address = 'http://{}:{}/'.format(match.group(1), int(match.group(2), 16))
            ret.add(address)
        return ret


class ProxynovaProxies(ProxySource):
    URL = 'http://www.proxynova.com/proxy-server-list/'
    _ANONYMOUS = False
    _MIN_SPEED = 5
    _RE_PATTERN = r'''((?:\d{1,3}\.){3}(?:\d{1,3}))'''

    def __init__(self, web):
        self.web = web

    async def getProxies(self):
        resp = await self.web.get(self.URL)
        tree = html.fromstring(resp.content)
        ret = set()
        for row in tree.xpath('//table[@id="tbl_proxy_list"]/tbody/tr'):
            tds = row.xpath('td')
            if len(tds) >= 6:
                # check speed, whatever "speed" is
                speed = convert(xpath_select(tds[3], 'div[@class="progress-bar"]/@data-value', strip=True), float,
                                default=0)
                if speed < self._MIN_SPEED:
                    continue
                # check if anonymous
                type = tds[6].text_content().strip()
                if self._ANONYMOUS and not (type == 'Anonymous' or type == 'Elite'):
                    continue
                ip = tds[0].text_content().strip()
                ip = re.search(self._RE_PATTERN, ip).group(1)
                port = tds[1].text_content().strip()
                address = 'http://{}:{}/'.format(ip, port)
                ret.add(address)
        return ret


class FreeproxylistProxies(ProxySource):
    URL = 'http://free-proxy-list.net/'
    _ANONYMOUS = False

    def __init__(self, web):
        self.web = web

    async def getProxies(self):
        resp = await self.web.get(self.URL)
        tree = html.fromstring(resp.content)
        ret = set()
        for row in tree.xpath('//table[@id="proxylisttable"]/tbody/tr'):
            ip = xpath_select(row, './td[1]/text()', strip=True)
            port = xpath_select(row, './td[2]/text()', strip=True)
            type = xpath_select(row, './td[5]/text()', strip=True)
            if self._ANONYMOUS and not (type == 'anonymous' or type == 'elite proxy'):
                continue
            address = 'http://{}:{}/'.format(ip.strip(), port.strip())
            ret.add(address)
        return ret


class WebAccessService(metaclass=ABCMeta):
    MAX_TIMEOUT = 120

    def __init__(self, timeout=MAX_TIMEOUT, user_agent=None):
        self.timeout = timeout
        self.user_agent = user_agent

    async def _get(self, *args, session=None, timeout=MAX_TIMEOUT, **kwargs):
        selected_session = session
        try:
            if session is None:
                selected_session = await self.get_session()
            with aiohttp.Timeout(timeout):
                async with aiohttp.ClientSession.get(selected_session, *args,
                                                     **kwargs) as resp:
                    resp.session = selected_session
                    resp.content = await resp.read()
                    return resp
        finally:
            if session is None:
                selected_session.close()

    @abstractmethod
    async def get(self, address, *args, **kwargs):
        raise NotImplementedError()

    def sync_get(self, *args, **kwargs):
        return run_async(self.get(*args, **kwargs))

    @abstractmethod
    async def get_session(self, *args, **kwargs):
        raise NotImplementedError()

    @abstractmethod
    def blacklist(self, session):
        raise NotImplementedError()


class DirectWebAccess(WebAccessService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def get_session(self, *args, **kwargs):
        skip_auto = kwargs.pop('skip_auto_headers', [])
        headers = kwargs.pop('headers', {})
        if self.user_agent is not None and 'User-Agent' not in headers:
            skip_auto.append('User-Agent')
            headers['User-Agent'] = self.user_agent() if callable(self.user_agent) else self.user_agent
        session = aiohttp.ClientSession(skip_auto_headers=skip_auto, headers=headers)
        session.get = functools.partial(self.get, self, session=session)
        return session

    async def get(self, address, *args, **kwargs):
        return await self._get(address, *args, **kwargs)

    def blacklist(self, session):
        raise NotImplementedError()


class ProxyWebAccess(WebAccessService):
    """Wraps one proxy in a class that that provides access through that proxy."""
    BAD_PROXY_EXCEPTIONS = (
        ConnectionResetError, aiohttp.ProxyConnectionError, aiohttp.HttpProxyError, aiohttp.errors.ContentEncodingError,
        aiohttp.errors.TransferEncodingError)
    DELAY_BASE = 2
    DELAY_EXPONENT = 5
    MAX_EXPONENT = 15
    MEASURE_PERIOD = 5
    MAINTAIN_RATIO_THRESHOLD = 0.05
    REDUCE_RATIO_THRESHOLD = 0.08
    MAX_REQUEST_INCREMENT = 5
    AGING_FACTOR = 0.95

    def __init__(self, *args, proxy, test_url='http://google.com/', **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy = proxy
        self._test_url = test_url
        self._max_requests = self.MAX_REQUEST_INCREMENT
        self._request_semaphore = asyncio.Semaphore(value=0)
        self._successful_requests = 0
        self._unsuccessful_requests = 0
        self._most_successful_requests = 0
        self._delay_exponent = self.DELAY_EXPONENT
        asyncio.ensure_future(self._test())

    def _assess_result(self, result):
        if result is None \
                or isinstance(result, self.BAD_PROXY_EXCEPTIONS + FAIL_EXCEPTION_TYPES) \
                or not hasattr(result, 'content'):
            return False
        else:
            return True

    async def _measure_rate(self):
        requests = self._successful_requests + self._unsuccessful_requests
        if requests == 0:
            new_max_requests = self._max_requests
        elif self._successful_requests == 0:
            new_max_requests = 0
        else:
            error_ratio = self._unsuccessful_requests / requests
            self._most_successful_requests = max(self._most_successful_requests, self._successful_requests)
            if error_ratio < self.MAINTAIN_RATIO_THRESHOLD \
                    and self._successful_requests >= self._most_successful_requests:
                new_max_requests = self._max_requests + self.MAX_REQUEST_INCREMENT
            elif error_ratio < self.REDUCE_RATIO_THRESHOLD:
                new_max_requests = self._max_requests
                # aging element
                self._most_successful_requests = int(self._most_successful_requests * self.AGING_FACTOR)
            else:
                new_max_requests = self._max_requests // 2
                # aging element
                self._most_successful_requests = int(self._most_successful_requests * self.AGING_FACTOR)
        semaphore_change = new_max_requests - self._max_requests
        if semaphore_change > 0:
            for i in range(semaphore_change):
                self._request_semaphore.release()
        else:
            for i in range(abs(semaphore_change)):
                await self._request_semaphore.acquire()
        self._max_requests = new_max_requests
        self._successful_requests = 0
        self._unsuccessful_requests = 0
        if self._max_requests == 0:
            delayed_ensure_future(self._test(), self.DELAY_BASE ** self._delay_exponent)
        else:
            delayed_ensure_future(self._measure_rate(), self.MEASURE_PERIOD)

    async def _test(self):
        # TODO filter out content manipulating proxies?
        try:
            result = await self._get(self._test_url)
        except Exception as e:
            result = e
        if self._assess_result(result):
            # logger.debug('test of proxy %s succeeded', self._proxy)
            self._max_requests = self.MAX_REQUEST_INCREMENT
            for i in range(self._max_requests):
                self._request_semaphore.release()
            self._successful_requests = 0
            self._unsuccessful_requests = 0
            self._most_successful_requests = 0
            self._delay_exponent = self.DELAY_EXPONENT
            delayed_ensure_future(self._measure_rate(), self.MEASURE_PERIOD)
        else:
            # logger.debug('test of proxy %s failed, increasing delay exponentially', self._proxy)
            self._delay_exponent += 1
            if self._delay_exponent <= self.MAX_EXPONENT:
                delayed_ensure_future(self._test(), self.DELAY_BASE ** self._delay_exponent)

    @property
    def performance(self):
        return self._max_requests

    @property
    def proxy(self):
        return self._proxy

    async def get_session(self, *args, **kwargs):
        # TODO socks support
        # TODO auth support
        skip_auto = kwargs.pop('skip_auto_headers', [])
        headers = kwargs.pop('headers', {})
        if self.user_agent is not None and 'User-Agent' not in headers:
            skip_auto.append('User-Agent')
            headers['User-Agent'] = self.user_agent() if callable(self.user_agent) else self.user_agent
        connector = aiohttp.ProxyConnector(proxy=self._proxy, force_close=False, limit=1)
        session = aiohttp.ClientSession(connector=connector, skip_auto_headers=skip_auto, headers=headers)
        session.proxy = self._proxy
        session.get = functools.partial(self.get, session=session)
        return session

    async def get(self, address, *args, **kwargs):
        result = None
        try:
            self._request_semaphore.acquire()
            result = await self._get(address, *args, **kwargs)
            return result
        except self.BAD_PROXY_EXCEPTIONS + FAIL_EXCEPTION_TYPES as e:
            result = e
            raise
        except Exception:
            logger.exception('Unexpected Exception type while performing get request:')
            raise
        finally:
            if self._assess_result(result):
                self._successful_requests += 1
            else:
                self._unsuccessful_requests += 1
            self._request_semaphore.release()

    def blacklist(self, session):
        raise NotImplementedError()


class ProxyListService(WebAccessService):
    UPDATE_PERIOD = 15 * 60
    UPDATE_TIMEOUT = 3 * 60
    RAND_RANGE = 5 * 60
    TEST_URL = 'http://google.com/'
    DEFAULT_TIMEOUT = 15

    def __init__(self, timeout=DEFAULT_TIMEOUT):
        super().__init__(timeout)
        self.proxies_available_event = asyncio.Event()
        self._proxies = {}
        directAccess = DirectWebAccess()
        self._proxy_lists = [GatherProxyProxies(directAccess), FreeproxylistProxies(directAccess),
                             ProxynovaProxies(directAccess), SpysRuProxies(self), ProxyListsProxies(self)]
        asyncio.ensure_future(self._refresh_proxies())

    async def _refresh_proxylist(self, proxylist):
        try:
            proxies = await asyncio.wait_for(proxylist.getProxies(), timeout=self.UPDATE_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning('%s failed to provide any proxies', proxylist.URL)
            raise
        logger.info('Got %d proxies from %s', len(proxies), proxylist.URL)
        for proxy in proxies:
            if proxy not in self._proxies:
                self._proxies[proxy] = ProxyWebAccess(proxy=proxy, test_url=self.TEST_URL, timeout=self.timeout)
                self.proxies_available_event.set()
                self.proxies_available_event.clear()

    async def _refresh_proxies(self):
        logger.info('Getting proxies from proxy list websites')
        coros = []
        for proxylist in self._proxy_lists:
            coros.append(self._refresh_proxylist(proxylist))
        await asyncio.gather(*coros, return_exceptions=True)
        delayed_ensure_future(self._refresh_proxies(),
                              self.UPDATE_PERIOD + random.randrange(-self.RAND_RANGE, self.RAND_RANGE))

    @property
    def proxies(self):
        return dict(self._proxies)

    async def get_session(self, *args, **kwargs):
        proxy = kwargs.pop('proxy', None) or await self._random_proxy()
        skip_auto = kwargs.pop('skip_auto_headers', [])
        headers = kwargs.pop('headers', {})
        if self.user_agent is not None and 'User-Agent' not in headers:
            skip_auto.append('User-Agent')
            headers['User-Agent'] = self.user_agent() if callable(self.user_agent) else self.user_agent
        return await self._proxies[proxy].get_session(*args, skip_auto_headers=skip_auto, headers=headers, **kwargs)

    async def get(self, address, *args, **kwargs):
        return await self._get(address, *args, **kwargs)

    def blacklist(self, session):
        self._proxies.pop(session.proxy, None)

    async def _random_proxy(self):
        qualified_proxies = [k for k, v in self._proxies.items() if v.performance > 0]
        while len(qualified_proxies) == 0:
            await self.proxies_available_event.wait()
            qualified_proxies = [k for k, v in self._proxies.items() if v.performance > 0]
        return weighed_choice(qualified_proxies, lambda x: self._proxies[x].performance)


class ProxySessionService(WebAccessService):
    MAX_RETRIES = 1024

    def __init__(self, proxy_service, *args, proxy_change_after=2, blacklist_exception_types=(),
                 blacklist_response_codes=(), good_response_codes=(200,), **kwargs):
        super().__init__(*args, **kwargs)
        self._proxy_service = proxy_service
        self.proxy_change_after = proxy_change_after
        self._blacklist_exception_types = blacklist_exception_types
        self._blacklist_response_codes = blacklist_response_codes
        self._good_response_codes = good_response_codes
        self._blacklisted_proxies = set()
        self._netloc_to_sessions = {}

    async def get_session(self, address, *args, **kwargs):
        netloc = urlparse(address).netloc
        if netloc not in self._netloc_to_sessions:
            self._netloc_to_sessions[netloc] = []
        available_sessions = self._netloc_to_sessions[netloc]
        if available_sessions:
            return available_sessions.pop()
        else:
            skip_auto = kwargs.pop('skip_auto_headers', [])
            headers = kwargs.pop('headers', {})
            if self.user_agent is not None and 'User-Agent' not in headers:
                skip_auto.append('User-Agent')
                headers['User-Agent'] = self.user_agent() if callable(self.user_agent) else self.user_agent
            return await self._proxy_service.get_session(proxy=await self._random_proxy(),
                                                         skip_auto_headers=skip_auto, headers=headers)

    def return_session(self, session, address):
        netloc = urlparse(address).netloc
        self._netloc_to_sessions[netloc].append(session)

    async def _random_proxy(self):
        proxies = self._proxy_service.proxies
        qualified_proxies = [k for k, v in proxies.items() if v.performance > 0 and k not in self._blacklisted_proxies]
        while len(qualified_proxies) == 0:
            await self._proxy_service.proxies_available_event.wait()
            proxies = self._proxy_service.proxies
            qualified_proxies = [k for k, v in proxies.items()
                                 if v.performance > 0 and k not in self._blacklisted_proxies]
        return weighed_choice(qualified_proxies, lambda x: proxies[x].performance)

    async def get(self, address, *args, **kwargs):
        session = await self.get_session(address)
        result = None
        retries = 0
        while retries < self.MAX_RETRIES:
            retries += 1
            blacklist_proxy = False
            result = None
            try:
                # logger.debug('GET %s', address)
                result = await session.get(address, *args, timeout=self.timeout, **kwargs)
                if result.status in self._blacklist_response_codes:
                    blacklist_proxy = True
                elif result is not None and hasattr(result,
                                                    'content') and result.status in self._good_response_codes:
                    break
            except self._blacklist_exception_types as e:
                result = e
                blacklist_proxy = True
            except FAIL_EXCEPTION_TYPES as e:
                result = e
            if blacklist_proxy:
                self.blacklist(session)
                # logger.debug('Query to %s failed, retrying, blacklisted proxy %s', address, session.proxy)
                session.close()
                session = await self.get_session(address)
            elif retries % self.proxy_change_after == 0:
                # logger.debug('Query to %s failed, retrying, changing proxy', address)
                session.close()
                session = await self.get_session(address)
            else:
                pass
                # logger.debug('Query to %s failed, retrying', address)
            await asyncio.sleep(0.25)
        else:
            session.close()
            logger.debug('Query to %s failed in %d retries, abandoning', address, self.MAX_RETRIES)
            if isinstance(result, Exception):
                raise result
            else:
                return result
        self.return_session(session, address)
        return result

    def blacklist(self, session):
        self._blacklisted_proxies.add(session.proxy)


class BaseTorService(WebAccessService):
    MIN_BANDWIDTH = 56
    KILL_TIMEOUT = 15
    CIRCUIT_WAIT_TIMEOUT = 20
    CIRCUIT_CHECK_DELAY = 0.02
    CIRCUIT_RETRIES = 5
    MAX_SIMULTANEOUS_CIRCUIT_REQUESTS = 4

    def __init__(self, control_port, socks_port, data_directory, *args, circuit_number=0, **kwargs):
        super().__init__(*args, **kwargs)
        self._destroyed = False
        self._loop = asyncio.get_event_loop()
        self.socks_port = socks_port
        config = {
            'ControlPort': str(control_port),
            'SOCKSPort': str(socks_port),
            'DataDirectory': data_directory,
            '__LeaveStreamsUnattached': '1',
            'NewCircuitPeriod': '31536000',
            'MaxCircuitDirtiness': '31536000',
            'CookieAuthentication': '1',
            'FetchDirInfoEarly': '1',
            'FetchDirInfoExtraEarly': '1',
            'FetchUselessDescriptors': '1',
            'UseMicrodescriptors': '0',
            'DownloadExtraInfo': '1',
        }
        self._tor_process = process.launch_tor_with_config(config)
        self._controller = control.Controller.from_port(port=control_port)
        self._controller.authenticate()
        self._controller.set_conf('__DisablePredictedCircuits', '1')
        stem.util.log.get_logger().setLevel(logging.ERROR)
        self._exit_nodes = None
        self._relay_nodes = None
        self._selected_circuit_id = 0
        self._circuit_ids = {}
        self._circuit_creation_semaphore = asyncio.Semaphore(value=self.MAX_SIMULTANEOUS_CIRCUIT_REQUESTS)
        self._circuits_available_event = asyncio.Event()
        self._controller.add_event_listener(self._handle_new_circuit, control.EventType.CIRC)
        self._controller.add_event_listener(self._attach_stream, control.EventType.STREAM)
        asyncio.ensure_future(self._init_coro(circuit_number))

    async def _init_coro(self, circuit_number):
        await self._get_tor_statuses()
        coroutines = []
        for i in range(circuit_number):
            coroutines.append(self.create_circuit())
        await asyncio.gather(*coroutines, return_exceptions=True)

    def __del__(self):
        # TODO __del__ is unreliable, context managers are inappropriate
        if not self._destroyed:
            logger.warning('%s not destroyed, destroying in __del__', type(self).__name__)
            self._destroy()

    @property
    def circuit_ids(self):
        return dict(self._circuit_ids)

    @property
    def relay_nodes(self):
        return list(self._relay_nodes)

    @property
    def exit_nodes(self):
        return list(self._exit_nodes)

    def _destroy(self):
        if not self._destroyed:
            self._destroyed = True
            if hasattr(self, '_circuit_ids'):
                for circuit_id in self._circuit_ids:
                    self._controller.close_circuit(circuit_id)
                self._controller.remove_event_listener(self._handle_new_circuit)
                self._controller.remove_event_listener(self._attach_stream)
                self._controller.__exit__(None, None, None)
            if hasattr(self, '_tor_process'):
                try:
                    self._tor_process.terminate()
                    self._tor_process.wait(timeout=self.KILL_TIMEOUT)
                except TimeoutExpired:
                    logger.warning('Tor process refused to terminate, killing')
                    self._tor_process.kill()

    def _attach_stream(self, stream_event):
        # logger.debug('(StreamEvent)id: %s; status: %s; circ_id: %s; target: %s; reason: %s; remote_reason: %s'
        #              '; source: %s; source_addr: %s; purpose: %s', stream_event.id, stream_event.status,
        #              stream_event.circ_id, stream_event.target, stream_event.reason, stream_event.remote_reason,
        #              stream_event.source, stream_event.source_addr, stream_event.purpose)
        # a cruel hack - no simple way to pair a tor stream with aiohttp session
        if stream_event.status == 'NEW':
            if self._selected_circuit_id != 0 and self._selected_circuit_id in self._circuit_ids:
                circuit_id = self._selected_circuit_id
            else:
                if self._circuit_ids:
                    circuit_id = random.choice(tuple(self._circuit_ids.keys()))
                    logger.warning('selected_circuit_id not set, picked a random id: %s', circuit_id)
                else:
                    path = [weighed_choice(self._relay_nodes, lambda x: x.bandwidth).fingerprint,
                            weighed_choice(self._exit_nodes, lambda x: x.bandwidth).fingerprint]
                    circuit_id = self._controller.new_circuit(path, await_build=True)
                    logger.error('No circuits available, created a new 2-hop one: %s', circuit_id)
            self._controller.attach_stream(stream_event.id, circuit_id)

    def _handle_new_circuit(self, circuit_event):
        # logger.debug('(CircuitEvent); id: %s; status: %s; path: %s; build_flags: %s; purpose: %s; hs_state: %s; '
        #              'rend_query: %s; created: %s; reason: %s; remote_reason: %s; '
        #              'socks_username: %s; socks_password: %s', circuit_event.id, circuit_event.status,
        #              circuit_event.path, circuit_event.build_flags, circuit_event.purpose, circuit_event.hs_state,
        #              circuit_event.rend_query, circuit_event.created, circuit_event.reason,
        #              circuit_event.remote_reason, circuit_event.socks_username, circuit_event.socks_password)
        if circuit_event.status == CircStatus.BUILT:
            self._circuit_ids[circuit_event.id] = circuit_event
        elif circuit_event == CircStatus.CLOSED:
            del self._circuit_ids[circuit_event.id]
        elif circuit_event == CircStatus.FAILED:
            pass

    async def _get_tor_statuses(self):
        self._exit_nodes = []
        self._relay_nodes = []
        descriptors = await self._loop.run_in_executor(None, self._controller.get_network_statuses)
        for desc in descriptors:
            if desc.bandwidth > self.MIN_BANDWIDTH:
                if desc.exit_policy is not None and desc.exit_policy.is_exiting_allowed():
                    self._exit_nodes.append(desc)
                else:
                    self._relay_nodes.append(desc)
        self._exit_nodes.sort(key=lambda x: x.bandwidth, reverse=True)
        self._relay_nodes.sort(key=lambda x: x.bandwidth, reverse=True)
        delayed_ensure_future(self._get_tor_statuses(), 60 * 60)

    async def _random_circuit(self):
        if not self._circuit_ids:
            await self._circuits_available_event.wait()
        return random.choice(tuple(self._circuit_ids.keys()))

    async def _wait_for_circuit(self, id):
        while id not in self._circuit_ids:
            await asyncio.sleep(self.CIRCUIT_CHECK_DELAY)
        else:
            self._circuits_available_event.set()
            self._circuits_available_event.clear()

    async def create_circuit(self, *, path=None, length=2):
        retries = self.CIRCUIT_RETRIES
        while retries:
            retries -= 1
            try:
                await self._circuit_creation_semaphore.acquire()
                if path is None:
                    # select a random (weighed) path
                    path = []
                    for i in range(length - 1):
                        path.append(weighed_choice(self._relay_nodes, lambda x: x.bandwidth).fingerprint)
                    path.append(weighed_choice(self._exit_nodes, lambda x: x.bandwidth).fingerprint)
                # create a circuit
                new_id = self._controller.new_circuit(path, await_build=False)
                await asyncio.wait_for(self._wait_for_circuit(new_id), self.CIRCUIT_WAIT_TIMEOUT)
                logger.debug('Created a circuit with id %s', new_id)
                return
            except asyncio.TimeoutError:
                logger.debug('Creating a circuit took too long, retrying')
            except Exception:
                logger.warning('Error while creating a Tor circuit:', exc_info=True)
            finally:
                self._circuit_creation_semaphore.release()

    async def get(self, address, *args, session=None, **kwargs):
        if session is None:
            session = self.get_session()
        if session.circuit_id not in self._circuit_ids:
            session.circuit_id = random.choice(tuple(self._circuit_ids.keys()))
        self._selected_circuit_id = session.circuit_id
        return await super()._get(address, *args, session=session, **kwargs)

    async def get_session(self, *args, **kwargs):
        circuit_id = kwargs.pop('circuit_id', None)
        skip_auto = kwargs.pop('skip_auto_headers', [])
        headers = kwargs.pop('headers', {})
        if self.user_agent is not None and 'User-Agent' not in headers:
            skip_auto.append('User-Agent')
            headers['User-Agent'] = self.user_agent() if callable(self.user_agent) else self.user_agent
        socks_proxy = aiosocks.Socks5Addr('127.0.0.1', self.socks_port)
        # note very important limit parameter, thanks to this session can be bound to particular circuit id
        connector = SocksConnector(proxy=socks_proxy, remote_resolve=False, force_close=False, limit=1)
        session = aiohttp.ClientSession(connector=connector, skip_auto_headers=skip_auto, headers=headers)
        if circuit_id:
            session.circuit_id = circuit_id
        elif not self._circuit_ids and circuit_id is None:
            raise IndexError('No circuits in self.circuit_ids')
        else:
            session.circuit_id = random.choice(tuple(self._circuit_ids))
        session.get = functools.partial(self.get, session=session)
        return session

    async def close_session_circuit(self, session):
        if session.circuit_id in self._circuit_ids:
            await self._loop.run_in_executor(None, self._controller.close_circuit, session.circuit_id)
        if session.circuit_id == self._selected_circuit_id:
            self._selected_circuit_id = random.choice(tuple(self._circuit_ids))
        session.close()

    def blacklist(self, session):
        raise NotImplementedError


class TorSessionService(WebAccessService):
    MAX_RETRIES = 100

    def __init__(self, tor_service, *args, optimal_circuit_number=25, retry_timeout=0.25, circuit_reset_after=2,
                 blacklist_exception_types=(), blacklist_response_codes=(), good_response_codes=(200,), **kwargs):
        super().__init__(*args, **kwargs)
        self._tor_service = tor_service
        self._optimal_circuit_number = optimal_circuit_number
        self.retry_timeout = retry_timeout
        self.circuit_reset_after = circuit_reset_after
        self._blacklist_exception_types = blacklist_exception_types
        self._blacklist_response_codes = blacklist_response_codes
        self._good_response_codes = good_response_codes
        self._blacklisted_exit_nodes = set()
        self._acceptable_circuits = {}
        self._restoring = False
        self._netloc_to_sessions = {}
        asyncio.ensure_future(self._restore_circuit_count())

    @property
    def optimal_circuit_number(self):
        return self._optimal_circuit_number

    @optimal_circuit_number.setter
    def optimal_circuit_number(self, value):
        self._optimal_circuit_number = value
        asyncio.ensure_future(self._restore_circuit_count())

    async def _restore_circuit_count(self):
        relay_nodes = self._tor_service.relay_nodes
        exit_nodes = [node for node in self._tor_service.exit_nodes if
                      node.fingerprint not in self._blacklisted_exit_nodes]
        self._acceptable_circuits = tuple(k for k, v in self._tor_service.circuit_ids.items() if
                                          v.path[-1][0] not in self._blacklisted_exit_nodes)
        diff = self._optimal_circuit_number - len(self._acceptable_circuits)
        if diff > 0 and not self._restoring:
            self._restoring = True
            coros = []
            for i in range(diff):
                path = [weighed_choice(relay_nodes, lambda x: x.bandwidth).fingerprint,
                        weighed_choice(exit_nodes, lambda x: x.bandwidth).fingerprint]
                coros.append(self._tor_service.create_circuit(path=path))
            await asyncio.gather(*coros, return_exceptions=True)
            self._restoring = False

    async def get_session(self, address, *args, **kwargs):
        netloc = urlparse(address).netloc
        if netloc not in self._netloc_to_sessions:
            self._netloc_to_sessions[netloc] = []
        available_sessions = self._netloc_to_sessions[netloc]
        if available_sessions:
            return available_sessions.pop()
        else:

            return await self._tor_service.get_session(circuit_id=await self._random_circuit())

    def return_session(self, session, address):
        netloc = urlparse(address).netloc
        self._netloc_to_sessions[netloc].append(session)

    async def _random_circuit(self):
        await self._restore_circuit_count()
        self._acceptable_circuits = tuple(k for k, v in self._tor_service.circuit_ids.items() if
                                          v.path[-1][0] not in self._blacklisted_exit_nodes)
        return random.choice(self._acceptable_circuits)

    async def get(self, address, *args, **kwargs):
        session = await self.get_session(address)
        result = None
        retries = 0
        while retries < self.MAX_RETRIES:
            retries += 1
            change_circuit = False
            blacklist_endpoint = False
            result = None
            try:
                result = await session.get(address, *args, timeout=self.timeout, **kwargs)
                if result.status in self._blacklist_response_codes:
                    blacklist_endpoint = True
                elif result is not None and hasattr(result, 'content') and result.status in self._good_response_codes:
                    break
            except self._blacklist_exception_types as e:
                result = e
                if retries % self.circuit_reset_after == 0:
                    blacklist_endpoint = True
            except FAIL_EXCEPTION_TYPES as e:
                result = e
                if retries % self.circuit_reset_after == 0:
                    change_circuit = True
            if blacklist_endpoint:
                self.blacklist(session)
                logger.debug('Query to %s failed, retrying, blacklisted exit node of circuit %s', address,
                             session.circuit_id)
                session = await self.get_session(address)
            elif change_circuit:
                asyncio.ensure_future(self._tor_service.close_session_circuit(session))
                logger.debug('Query to %s failed, retrying, changing circuit to %s', address,
                             session.circuit_id)
                session = await self.get_session(address)
            else:
                logger.debug('Query to %s failed, retrying', address)
            await asyncio.sleep(0.25)
        else:
            logger.debug('Query to %s failed in %d retries, abandoning', address, self.MAX_RETRIES)
            if isinstance(result, Exception):
                raise result
            else:
                return result
        self.return_session(session, address)
        return result

    def blacklist(self, session):
        self._blacklisted_exit_nodes.add(self._tor_service.circuit_ids[session.circuit_id].path[-1][0])
        asyncio.ensure_future(self._tor_service.close_session_circuit(session))
        asyncio.ensure_future(self._restore_circuit_count())
