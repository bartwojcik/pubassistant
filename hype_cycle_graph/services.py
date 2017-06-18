import logging

from django.db import connection
from haystack.query import SearchQuerySet

from main_assistant.models import Keyword, Publication
from main_assistant.utils import convert

LIMIT_KEYWORD_SEARCH = 100
LIMIT_PUBLICATION_SEARCH = 50

logger = logging.getLogger(__name__)


def search_publications(submitted_text):
    sqs_results = SearchQuerySet().models(Publication).filter(name=submitted_text).filter(is_journal=True).load_all()[
                  0:LIMIT_PUBLICATION_SEARCH]
    results = [r.object for r in sqs_results]
    return results


def search_keywords(submitted_text):
    sqs_results = SearchQuerySet().models(Keyword).filter(content=submitted_text).load_all()[0:LIMIT_KEYWORD_SEARCH]
    results = [r.object for r in sqs_results]
    return results


def get_hype_graph_data(keyword_id, journal_ids=None):
    cursor = connection.cursor()
    # reset_queries()
    if journal_ids is None:
        cursor.execute('''
        SELECT (EXTRACT(year FROM issue_date)) AS "year", COUNT("main_assistant_article"."id") AS "num"
        FROM "main_assistant_article"
        INNER JOIN "main_assistant_article_keywords"
            ON ("main_assistant_article"."id" = "main_assistant_article_keywords"."article_id")
        WHERE ("main_assistant_article_keywords"."keyword_id" = %s)
        GROUP BY (EXTRACT(year FROM issue_date));
        ''', [keyword_id])
    else:
        cursor.execute('''
        SELECT (EXTRACT(year FROM issue_date)) AS "year", COUNT("main_assistant_article"."id") AS "num"
        FROM "main_assistant_article"
        INNER JOIN "main_assistant_article_keywords"
            ON ("main_assistant_article"."id" = "main_assistant_article_keywords"."article_id")
        WHERE ("main_assistant_article_keywords"."keyword_id" = %s
            AND "main_assistant_article"."publication_id" IN (SELECT U0."id"
                                                              FROM "main_assistant_publication" U0
                                                              WHERE U0."id" IN %s))
        GROUP BY (EXTRACT(year FROM issue_date));
        ''', [keyword_id, tuple(iden for iden in journal_ids)])
    # logger.debug('{}'.format(connection.queries))
    res_dict = {convert(row[0], int): row[1] for row in cursor.fetchall()}
    return res_dict
