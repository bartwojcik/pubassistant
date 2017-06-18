import logging
from collections import namedtuple

from haystack.query import SearchQuerySet

from main_assistant.models import Author, Reference

LIMIT_AUTHOR_SEARCH = 100
MIN_SIMILARITY = 0.30

logger = logging.getLogger(__name__)


def search_authors(submitted_name):
    sqs_results = SearchQuerySet().models(Author).filter(content=submitted_name).load_all()[0:LIMIT_AUTHOR_SEARCH]
    results = [r.object for r in sqs_results]
    return results


referrer_entry = namedtuple('referrer_entry', ['author', 'references'])  # references TO author's papers
coreferrer_entry = namedtuple('Coreferrer_entry',
                              ['author', 'references', 'backreferences'])  # and backreferences FROM author


def find_referred_authors(original_author, sought_author=None):
    references = Reference.objects.select_related('referring', 'referred') \
        .prefetch_related('referred__authors').filter(referring__authors=original_author)
    referred_authors = {}
    for reference in references:
        for author in reference.referred.authors.all():
            if sought_author is None or author == sought_author:
                if author.pk not in referred_authors:
                    referred_authors[author.pk] = referrer_entry(author, set())
                referred_authors[author.pk].references.add(reference)
    return list(referred_authors.values())


def find_coreferrers(original_author):
    references = Reference.objects.select_related('referring', 'referred').prefetch_related('referred__authors') \
        .filter(referring__authors=original_author)
    backreferences = Reference.objects.select_related('referring', 'referred').prefetch_related('referred__authors') \
        .filter(referred__authors=original_author)
    cited_authors = {}
    for reference in references:
        for author in reference.referred.authors.all():
            if author.pk not in cited_authors:
                cited_authors[author.pk] = coreferrer_entry(author, set(), set())
            cited_authors[author.pk].references.add(reference)
    for backreference in backreferences:
        for author in backreference.referring.authors.all():
            if author != original_author:
                if author.pk not in cited_authors:
                    cited_authors[author.pk] = coreferrer_entry(author, set(), set())
                cited_authors[author.pk].backreferences.add(backreference)
    coreferrers = [entry for entry in cited_authors.values() if len(entry.references) and len(entry.backreferences)]
    coreferrers.sort(key=lambda x: (len(x.references) + len(x.backreferences)) *
                                   len(x.references) * len(x.backreferences), reverse=True)
    return coreferrers
