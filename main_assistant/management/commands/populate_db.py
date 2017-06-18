from django.core.management.base import BaseCommand

import main_assistant.services


class Command(BaseCommand):
    args = ''
    help = 'Populates the Database with needed data.'

    def _populate(self):
        for provider in main_assistant.services.BaseProvider.__subclasses__():
            provider.get_or_create()

    def handle(self, *args, **options):
        self._populate()
