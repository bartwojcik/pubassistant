import asyncio
import functools
import hashlib
import logging
import random
import re
from abc import ABCMeta, abstractmethod
from datetime import datetime
from urllib.parse import urljoin

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F
from django.utils.functional import SimpleLazyObject
from lxml import etree, html
from lxml.etree import ParserError
from lxml.etree import XMLSyntaxError
from user_agent import generate_user_agent

from main_assistant.models import Publication, Author, Keyword, Article, Reference, SavedReference, DownloadBlock, \
    DigitalLibrary
from main_assistant.network import ProxySessionService, ProxyListService
from main_assistant.utils import run_async, xpath_select, convert, get_url_param, remove_url_params

logger = logging.getLogger(__name__)


class NoContentException(Exception):
    """Page has no scrapable content."""
    pass


class ScrapException(Exception):
    """Item cannot be scraped (possibly because some elements are missing)."""
    pass


class ContentDistortedException(Exception):
    """Service is providing distorted content."""

    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


proxyListService = SimpleLazyObject(ProxyListService)


# proxyListService = ProxyListService()


class BaseProvider(metaclass=ABCMeta):
    """Base interface for publication search engines."""

    @classmethod
    def get_or_create(cls):
        instance, created = DigitalLibrary.objects.get_or_create(name=cls.PROVIDER_NAME, defaults={'total_articles': 0})
        return instance

    @classmethod
    def merge_download_blocks(cls, digital_library):
        with transaction.atomic():
            digital_library = digital_library or cls.get_or_create()
            blocks = digital_library.sorted_blocks
            if blocks:
                i = 1
                previous = blocks[0]
                while i < len(blocks):
                    current = blocks[i]
                    if previous.start + previous.size >= current.start:
                        previous.size = max(previous.start + previous.size,
                                            current.start + current.size) - previous.start
                        previous.save()
                        current.delete()
                    else:
                        previous = current
                    i += 1

    @classmethod
    @abstractmethod
    def update_status(cls):
        raise NotImplementedError

    @classmethod
    def download_status(cls):
        instance = cls.get_or_create()
        return instance.processed_block_articles, instance.total_articles

    @classmethod
    @abstractmethod
    async def download_article(cls, number):
        raise NotImplementedError

    @classmethod
    async def download_block_coroutine(cls, start, size):
        coroutines_group = []
        for i in range(size):
            coroutines_group.append(cls.download_article(start + i))
        results = await asyncio.gather(*coroutines_group, return_exceptions=True)
        await asyncio.get_event_loop().run_in_executor(None, cls.mark_as_processed, start, size)
        unsuccessful = sum(1 for res in results if isinstance(res, BaseException))
        logger.info('%s has finished the processing of block: (%d, %d), unsuccessful: %d', cls.__name__, start,
                    start + size, unsuccessful)
        return results

    @classmethod
    async def download_articles_coroutine(cls):

        def split_generator(current, diff):
            end = current + diff
            while current < end:
                size = min(cls.ARTICLES_PER_COROUTINE, end - current)
                yield cls.download_block_coroutine(current, size)
                current += size

        def group_generator():
            instance = cls.get_or_create()
            current = 0
            # holes
            for block in instance.sorted_blocks:
                # space before current block
                diff = block.start - current
                if diff > 0:
                    yield from split_generator(current, diff)
                # update end marker
                current = block.start + block.size
            # new ones
            diff = instance.total_articles - current
            if diff > 0:
                yield from split_generator(current, diff)

        # generator = group_generator()
        pending = set()

        async def await_one():
            nonlocal pending
            try:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            except Exception:
                logger.exception('Exception while processing block:')

        for group in group_generator():
            pending.add(group)
            if len(pending) >= cls.MAX_COROUTINES_ACTIVE:
                await await_one()
        while pending:
            await await_one()

    @classmethod
    def download_articles(cls):
        lock_name = '{}_scraping_task_lock'.format(cls.__name__)
        acquire_lock = lambda: cache.add(lock_name, 'true')
        release_lock = lambda: cache.delete(lock_name)
        if acquire_lock():
            logger.info('Starting scraping task for %s', cls.__name__)
            try:
                if cls.update_status():
                    run_async(cls.download_articles_coroutine())
            finally:
                release_lock()
            logger.info('Completed scraping task for %s', cls.__name__)
        else:
            logger.warning('Could not start scraping task for  %s - already running', cls.__name__)

    @classmethod
    def mark_as_processed(cls, start, size):
        with transaction.atomic():
            block = DownloadBlock()
            block.library = cls.get_or_create()
            block.start = start
            block.size = size
            block.save()

    @classmethod
    @abstractmethod
    def add_single_document(cls, document_r):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def add_referenced_document(cls, document_r):
        raise NotImplementedError

    @classmethod
    def process_saved_references(cls, article, internal_identifier):
        saved_references = SavedReference.objects.filter(referred_location=internal_identifier,
                                                         referred_location_is_internal_identifier=True,
                                                         referring__publication__digital_library__name=cls.PROVIDER_NAME)
        references = []
        for saved_reference in saved_references:
            referring = saved_reference.referring
            references.append(Reference(referring=referring, referred=article))
        Reference.objects.bulk_create(references)
        saved_references.delete()

    @classmethod
    async def add_reference(cls, article, url):
        loop = asyncio.get_event_loop()
        ref = None
        try:
            document = await document_from_url(url)
            if document:
                ref = await loop.run_in_executor(None,
                                                 functools.partial(Reference.objects.get_or_create,
                                                                   referring=article,
                                                                   referred=document))
        except Exception:
            logger.exception(
                "Exception thrown while processing a reference with url: {}\n from document {}:".format(
                    url, article.location))
            raise
        return ref


providers_map = {provider.PROVIDER_NAME: provider for provider in BaseProvider.__subclasses__()}
url_providers_map = {provider.URL_PATTERN: provider for provider in BaseProvider.__subclasses__()}


async def document_from_url(url):
    loop = asyncio.get_event_loop()
    web = random.choice([provider.web for provider in BaseProvider.__subclasses__()])
    while True:
        try:
            r = await web.get(url)
            final_url = r.url
            provider = await loop.run_in_executor(None, select_provider, final_url)
            if provider:
                return await provider.add_referenced_document(r)
            else:
                return
        except NoContentException:
            logger.debug('url: %s has no content', url)
            return
        except ContentDistortedException as e:
            web.blacklist(e.session)
        except Exception:
            logger.info('Failed to get document from url: %s', url)
            raise


def select_provider(url):
    for pattern, provider in url_providers_map.items():
        if re.search(pattern, url) and provider.get_or_create().enabled:
            return provider


def saved_reference_sweep():
    # TODO test, run
    for saved_ref in SavedReference.objects.all():
        ref = run_async(BaseProvider.add_reference(saved_ref.referring, saved_ref.referred_location))
        if isinstance(ref, Reference):
            saved_ref.delete()
