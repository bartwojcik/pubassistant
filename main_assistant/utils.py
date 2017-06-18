import asyncio
import collections
import inspect
import random
import re
from enum import Enum
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

import django.db.models.query
from lxml.etree import XPathEvalError
from rest_framework import status
from rest_framework.response import Response


def run_async(coroutine):
    return asyncio.get_event_loop().run_until_complete(coroutine)


def delayed_ensure_future(coroutine, delay):
    async def delay_coroutine(coroutine):
        await asyncio.sleep(delay)
        await coroutine

    return asyncio.ensure_future(delay_coroutine(coroutine))


def weighed_choice(choices, weight_fun):
    if not choices:
        raise IndexError('choices is empty')
    weight_map = {choice_index: weight_fun(choice) for choice_index, choice in enumerate(choices)}
    total = sum(weight for weight in weight_map.values())
    r = random.uniform(0, total)
    summed = 0
    for choice_index, choice in enumerate(choices):
        summed += weight_map[choice_index]
        if r <= summed:
            return choice
    return random.choice(choices)


async def backoff(coroutine, timeout, retries, backoff_for, on_fail=None, fail_exception_types=None):
    while retries > 0:
        try:
            return await asyncio.wait_for(coroutine, timeout)
        except Exception as e:
            caught = False
            for etype in fail_exception_types:
                if isinstance(e, etype):
                    caught = True
            if isinstance(e, asyncio.TimeoutError) or caught:
                if on_fail:
                    await asyncio.gather(asyncio.sleep(backoff_for), on_fail, return_exceptions=True)
                else:
                    await asyncio.sleep(backoff_for)
            else:
                raise
        retries -= 1


def xpath_select(element, path, index=0, default=None, extract_text=False, strip=None, regex=None, namespaces=None):
    try:
        resultset = element.xpath(path, namespaces=namespaces)
        result = resultset[index]
        if extract_text:
            result = result.text_content()
        if strip is True or extract_text and strip is not False:
            result = result.strip()
        if regex:
            result = re.search(regex, result).group()
        return result
    except (ValueError, TypeError, IndexError, AttributeError, XPathEvalError):
        return default


def remove_url_params(url, params):
    """Removes a list of params from """
    u = urlparse(url)
    query = parse_qs(u.query)
    if isinstance(params, collections.Iterable):
        for param in params:
            try:
                query.pop(param, None)
            except KeyError:
                pass
    else:
        try:
            query.pop(params, None)
        except KeyError:
            pass
    u = u._replace(query=urlencode(query, True))
    return urlunparse(u)


def get_url_param(url, param, default=None):
    try:
        return parse_qs(urlparse(url).query)[param][0]
    except (KeyError, IndexError):
        return default


def convert(val, con, *args, default=None):
    try:
        return con(val, *args)
    except (ValueError, TypeError):
        return default


class ChoiceEnum(Enum):
    @classmethod
    def choices(cls):
        members = inspect.getmembers(cls, lambda m: not (inspect.isroutine(m)))
        props = [m for m in members if not (m[0][:2] == '__')]
        # format into django choice tuple
        choices = tuple([(str(p[1].value), p[0]) for p in props])
        return choices


class RangeHeaderPaginator():
    MAX_PAGINATION_SIZE = 1000

    def __init__(self, objects, SerializerClass=None, max_size=MAX_PAGINATION_SIZE):
        self.objects = objects
        self.SerializerClass = SerializerClass
        self.max_size = max_size

    def get_response(self, request):
        range_str = request.META.get('HTTP_RANGE')
        headers = {}
        if range_str:
            accept_ranges_type = range_str.split('=')[0]
            if accept_ranges_type != 'items':
                return Response('Range header type not supported', status=status.HTTP_400_BAD_REQUEST)
            try:
                start = int(range_str.split('=')[1].split('-')[0])
                end = int(range_str.split('=')[1].split('-')[1]) + 1  # exclusive end
            except (ValueError, TypeError):
                return Response('Range header invalid value types', status=status.HTTP_400_BAD_REQUEST)
            if start >= end or start < 0:
                return Response('Range header invalid value',
                                status=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
            if end - start > self.max_size:
                return Response('Range header size too large', status=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
            if getattr(self.objects, 'hits', None) is not None and callable(self.objects.hits):
                self.objects = self.objects[start:end]
                content_size = self.objects.hits()
            elif isinstance(self.objects, django.db.models.query.QuerySet):
                content_size = self.objects.count()
                self.objects = self.objects[start:end]
            elif isinstance(self.objects, django.db.models.query.RawQuerySet):
                content_size = len(list(self.objects))
                self.objects = self.objects[start:end]
            else:
                content_size = len(self.objects)
                self.objects = self.objects[start:end]
            end = min(content_size, end)
            headers['Content-Range'] = 'items {}-{}/{}'.format(start, end + 1, content_size)
            headers['Accept-Ranges'] = 'items'
        if self.SerializerClass:
            return Response(self.SerializerClass(self.objects, many=True).data, headers=headers)
        else:
            return Response(self.objects, headers=headers)