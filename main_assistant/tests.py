from datetime import date

from django.db import transaction
from django.test import TestCase

# Create your tests here.
from unittest.mock import patch, PropertyMock, call

from lxml import html

from main_assistant.models import DigitalLibrary, DownloadBlock, Keyword, Author, Reference, Article
from main_assistant.services import BaseProvider

# TODO split when becomes too large
# TODO remove network access
# just love nondeterministic tests
# TODO split db tests
from main_assistant.utils import run_async


class BaseProviderTests(TestCase):
    def test_merge_download_blocks(self):
        with transaction.atomic():
            library = DigitalLibrary(name='TestDLibrary', total_articles=0)
            library.save()
            blocks = [DownloadBlock(start=1024, size=1024, library=library),
                      DownloadBlock(start=2048, size=1024, library=library),
                      DownloadBlock(start=4096, size=1024, library=library),
                      DownloadBlock(start=5120, size=1024, library=library)]
            DownloadBlock.objects.bulk_create(blocks)
        self.assertEqual(4, DownloadBlock.objects.filter(library=library).count())
        with transaction.atomic():
            BaseProvider.merge_download_blocks(library)
        self.assertEqual(2, DownloadBlock.objects.filter(library=library).count())
        blocks = library.sorted_blocks
        self.assertEqual(2048, blocks[0].size)
        self.assertEqual(2048, blocks[1].size)
        self.assertEqual(1024, blocks[0].start)
        self.assertEqual(4096, blocks[1].start)

    def test_schedule(self):
        with patch('main_assistant.services.download') as mock_update_articles:
            with patch.object(BaseProvider, 'ARTICLES_PER_TASK', create=True, new_callable=PropertyMock,
                              return_value=1000):
                with patch.object(BaseProvider, 'PROVIDER_NAME', create=True, new_callable=PropertyMock,
                                  return_value='BaseTest'):
                    BaseProvider.schedule(1000, 5500)
                    expected_calls = [call('BaseTest', 1000, 1000), call('BaseTest', 2000, 1000),
                                      call('BaseTest', 3000, 1000), call('BaseTest', 4000, 1000),
                                      call('BaseTest', 5000, 1000), call('BaseTest', 6000, 500)]
                    mock_update_articles.delay.assert_has_calls(expected_calls)
                    BaseProvider.schedule(0, 1000)
                    mock_update_articles.delay.assert_called_with('BaseTest', 0, 1000)

    def test_schedule_download(self):
        with transaction.atomic():
            library = DigitalLibrary(name='TestDLibrary', total_articles=7186)
            library.save()
            blocks = [DownloadBlock(start=1024, size=1024, library=library),
                      DownloadBlock(start=2048, size=1024, library=library),
                      DownloadBlock(start=4096, size=1024, library=library),
                      DownloadBlock(start=5120, size=1024, library=library), ]
            DownloadBlock.objects.bulk_create(blocks)
        with patch.object(BaseProvider, 'get_or_create') as mock_get_or_create:
            with patch('main_assistant.services.download') as mock_update_articles:
                with patch.object(BaseProvider, 'ARTICLES_PER_TASK', create=True, new_callable=PropertyMock,
                                  return_value=1024) as mock_apq:
                    with patch.object(BaseProvider, 'PROVIDER_NAME', create=True, new_callable=PropertyMock,
                                      return_value='BaseTest'):
                        with patch.object(BaseProvider, 'update_status') as mock_update_status:
                            mock_update_status.return_value = True
                            mock_get_or_create.return_value = library
                            BaseProvider.schedule_download()
                            expected_calls = [call('BaseTest', 0, 1024), call('BaseTest', 3072, 1024),
                                              call('BaseTest', 6144, 1024)]
                            mock_update_articles.delay.assert_has_calls(expected_calls)


