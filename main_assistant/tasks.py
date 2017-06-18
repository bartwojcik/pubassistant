from celery import shared_task
from celery.task.control import inspect

from main_assistant.models import DigitalLibrary


def scheduled_or_active_count(sought_task):
    count = 0
    for item in inspect().scheduled().items():
        for task in item[1]:
            if task['name'] == sought_task.name:
                count += 1
    for item in inspect().active().items():
        for task in item[1]:
            if task['name'] == sought_task.name:
                count += 1
    return count


@shared_task
def download(provider_name):
    from main_assistant.services import providers_map
    provider = providers_map[provider_name]
    provider.download_articles()


@shared_task
def update_articles(selected_provider_names):
    for provider_name in selected_provider_names:
        download.delay(provider_name)


@shared_task
def update_articles_periodic():
    enabled_dls = DigitalLibrary.objects.filter(enabled=True)
    enabled_provider_names = [dl.name for dl in enabled_dls]
    for provider_name in enabled_provider_names:
        if not scheduled_or_active_count(download):
            download.delay(provider_name)


@shared_task
def update_index_periodic():
    from haystack.management.commands import update_index
    update_index.Command().handle(batchsize=100000, remove=True, verbosity=2)


@shared_task
def trigger_reference_sweep():
    from main_assistant.services import saved_reference_sweep
    saved_reference_sweep()
