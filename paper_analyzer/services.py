import ahocorasick
import asyncio
import copy
import json
import logging
import re
import time
from abc import ABCMeta, abstractmethod
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal

import elasticsearch
from django.db import transaction
from haystack import connections
from haystack.constants import DJANGO_CT
from haystack.exceptions import NotHandled
from haystack.utils import get_model_ct
from lxml import html
from user_agent import generate_user_agent

from main_assistant.models import Keyword, Article, RankingType, Ranking, Publication
from main_assistant.network import DirectWebAccess
from main_assistant.utils import convert, xpath_select

logger = logging.getLogger(__name__)


class JournalRankingSource(metaclass=ABCMeta):
    @abstractmethod
    async def get_ranking(self, journal, ranking_type):
        pass


class WebJournalRankingSource(JournalRankingSource):
    _IMPACT_FACTOR_URL = 'http://www.scijournal.org/search/search.php?search=1'
    _MNISW_POINTS_DATES_URL = 'http://www.czasopismapunktowane.pl/'
    _MNISW_POINTS_URL = 'http://www.czasopismapunktowane.pl/data/search-data.php'
    _YEAR_PATTERN = r'(\d{4})'
    _CHECK_PERIOD = timedelta(days=7)

    def __init__(self, web):
        self._web = web
        self._impact_factor_most_recent_issue = None
        self._impact_factor_last_check = None
        self._mniws_points_most_recent_issue = None
        self._mniws_points_date_element = None
        self._mniws_points_last_check = None

    async def get_ranking(self, journal, ranking_type=None):
        if len(journal.identifier) > 9:
            return None
        else:
            if ranking_type is None:
                coros = []
                coros.append(self.get_impact_factor(journal))
                coros.append(self.get_mnisw(journal))
                results = await asyncio.gather(*coros, return_exceptions=True)
                return [ranking for ranking in results if ranking is not None]
            else:
                if ranking_type == RankingType.impact_factor:
                    return await self.get_impact_factor(journal)
                elif ranking_type == RankingType.mnisw_points:
                    return await self.get_mnisw(journal)
                else:
                    raise NotImplementedError('This type of ranking is not implemented by this source')

    async def get_mnisw(self, journal):
        if self._mniws_points_last_check is None or date.today() - self._mniws_points_last_check >= self._CHECK_PERIOD:
            res = await self._web.get(self._MNISW_POINTS_DATES_URL)
            tree = html.fromstring(res.content)
            date_elements = tree.xpath('//form[@id="myForm"]/input/@value')
            element_to_date = {}
            for elem in date_elements:
                date_string = re.search(self._YEAR_PATTERN, elem).group(1)
                element_to_date[elem] = datetime.strptime(date_string, '%Y').date()
            self._mniws_points_date_element = max(date_elements, key=lambda x: element_to_date[x])
            self._mniws_points_most_recent_issue = element_to_date[self._mniws_points_date_element]
            self.mniws_points_last_check = date.today()
        rank = Ranking.objects.filter(type=RankingType.mnisw_points, journal=journal).order_by('-date').first()
        if rank is None or rank.date < self._mniws_points_most_recent_issue:
            res = await self._web.get(self._MNISW_POINTS_URL, params={'searchData': journal.identifier,
                                                                      'whichList': self._mniws_points_date_element})
            tree = html.fromstring(res.content)
            points = convert(xpath_select(tree, '//table[@id="tabela"]/tbody/tr/td[3]', extract_text=True), Decimal)
            if points is None:
                return None
            else:
                rank, created = Ranking.objects.get_or_create(journal=journal, type=RankingType.mnisw_points.value,
                                                              date=self._mniws_points_most_recent_issue,
                                                              defaults={'value': points})
        return rank

    async def get_impact_factor(self, journal):
        update = False
        if self._impact_factor_last_check is None or date.today() - self._impact_factor_last_check >= self._CHECK_PERIOD:
            update = True
        rank = Ranking.objects.filter(type=RankingType.impact_factor, journal=journal).order_by('-date').first()
        if update or rank is None or rank.date < self._impact_factor_most_recent_issue:
            self._impact_factor_last_check = date.today()
            res = await self._web.get(self._IMPACT_FACTOR_URL, params={'query': journal.identifier})
            tree = html.fromstring(res.content)
            link = xpath_select(tree, '//div[@id="results"]/a/@href')
            if link is None:
                return None
            res = await self._web.get(link)
            tree = html.fromstring(res.content)
            extracted_texts = tree.xpath('//div[@id="main_content"]/center/h2/text()')
            extracted_text = '\n'.join(extracted_texts)
            date_to_impact_factor = {}
            for year, impact_factor in re.findall(r'(?:(\d{4})\s*Impact\sFactor\s*:\s*(\d+\.?\d*))', extracted_text):
                extracted_date = datetime.strptime(year, '%Y').date()
                date_to_impact_factor[extracted_date] = convert(impact_factor, Decimal)
            new_max_date = max(date_to_impact_factor.keys())
            if self._impact_factor_most_recent_issue is None or new_max_date > self._impact_factor_most_recent_issue:
                self._impact_factor_most_recent_issue = new_max_date
            rank, created = Ranking.objects.get_or_create(journal=journal, type=RankingType.impact_factor.value,
                                                          date=self._impact_factor_most_recent_issue,
                                                          defaults={'value': date_to_impact_factor[new_max_date]})
        return rank


ranking_source = WebJournalRankingSource(DirectWebAccess(user_agent=generate_user_agent))
automaton = None


def build_automaton():
    global automaton
    logger.debug('Building keyword automaton')
    start = time.time()
    qualified_keywords = Keyword.objects.qualified_keywords_values()
    length = len(qualified_keywords)  # also evaluates the queryset
    logger.debug('Retrieved %d qualified keywords from database in %.5fs', length, time.time() - start)
    start = time.time()
    automaton = ahocorasick.Automaton(ahocorasick.STORE_LENGTH)
    for keyword in qualified_keywords:
        automaton.add_word(keyword)
    automaton.make_automaton()
    logger.debug('Automaton build took %.5fs', time.time() - start)


def get_automaton():
    global automaton
    if automaton is None:
        logger.debug('No keywords_automaton saved, building')
        build_automaton()
    return automaton


def extract_keywords(article_text, max_keywords=None):
    article_len = len(article_text)
    automaton = get_automaton()
    found_keywords = {}
    for index, length in automaton.iter(article_text.lower()):
        beg = index - length + 1
        end = index + 1  # not including
        keyword = article_text[beg:end]
        if (beg - 1 >= 0 and article_text[beg - 1].isalnum()) or (end < article_len and article_text[end].isalnum()):
            continue
        # logger.debug('found keyword "%s" on indices %d to %d', keyword, beg, end)
        found_keywords[keyword] = 1 if keyword not in found_keywords else found_keywords[keyword] + 1
    if max_keywords is not None:
        sorted_keywords = sorted(found_keywords.keys(), key=lambda k: found_keywords[k], reverse=True)
        found_keywords = {k: found_keywords[k] for k in sorted_keywords[0:max_keywords]}
    return found_keywords


MAX_KEYWORDS = 50
SCORE_THRESHOLD = 0.05


def tf_idf_art_search(max_keywords=MAX_KEYWORDS, score_threshold=SCORE_THRESHOLD):
    def search(text):
        keywords = extract_keywords(text)
        arguments = [(key, value) for key, value in keywords.items()]
        format_str = ','.join(('%s' for _ in range(len(arguments))))
        arguments.append(max_keywords)
        arguments.append(score_threshold)
        # using approximate total document count
        # see: https://wiki.postgresql.org/wiki/Count_estimate
        with transaction.atomic():
            results = Article.objects.raw('''
                CREATE TEMPORARY TABLE keywords_input_temp (
                    keyword varchar(255) not null,
                    occurs integer not null
                ) ON COMMIT DROP;
                INSERT INTO keywords_input_temp VALUES
                {};
                CREATE TEMPORARY TABLE keywords_sorted_temp
                ON COMMIT DROP
                AS SELECT main_assistant_keyword.*, (LOG((SELECT reltuples AS article_count
                                                          FROM pg_class
                                                          WHERE relname = 'main_assistant_article')
                                                       / main_assistant_keyword.occurrence_count) + 1)
                                                    * sqrt(keywords_input_temp.occurs) AS weight
                FROM main_assistant_keyword, keywords_input_temp
                WHERE keywords_input_temp.keyword = main_assistant_keyword.keyword
                ORDER BY weight DESC LIMIT %s;
                CREATE TEMPORARY TABLE articles_scored_temp
                ON COMMIT DROP
                AS SELECT main_assistant_article_keywords.article_id, SUM(keywords_sorted_temp.weight) as value
                FROM main_assistant_article_keywords, keywords_sorted_temp
                WHERE main_assistant_article_keywords.keyword_id = keywords_sorted_temp.id
                GROUP BY main_assistant_article_keywords.article_id
                ORDER BY value DESC;
                SELECT main_assistant_article.*, grouped_articles.value as value
                FROM main_assistant_article, (SELECT * FROM articles_scored_temp
                                              WHERE value > %s * (SELECT value
                                                                  FROM articles_scored_temp
                                                                  LIMIT 1)) AS grouped_articles
                WHERE main_assistant_article.id = grouped_articles.article_id;
            '''.format(format_str), arguments)
            return results

    return search


def tf_art_search(max_keywords=MAX_KEYWORDS, score_threshold=SCORE_THRESHOLD):
    def search(text):
        keywords = extract_keywords(text)
        arguments = [(key, value) for key, value in keywords.items()]
        format_str = ','.join(('%s' for _ in range(len(arguments))))
        arguments.append(max_keywords)
        arguments.append(score_threshold)
        # using approximate total document count
        # see: https://wiki.postgresql.org/wiki/Count_estimate
        with transaction.atomic():
            results = Article.objects.raw('''
                CREATE TEMPORARY TABLE keywords_input_temp (
                    keyword varchar(255) not null,
                    occurs integer not null
                ) ON COMMIT DROP;
                INSERT INTO keywords_input_temp VALUES
                {};
                CREATE TEMPORARY TABLE keywords_sorted_temp
                ON COMMIT DROP
                AS SELECT main_assistant_keyword.*, keywords_input_temp.occurs AS weight
                FROM main_assistant_keyword, keywords_input_temp
                WHERE keywords_input_temp.keyword = main_assistant_keyword.keyword
                ORDER BY weight DESC LIMIT %s;
                CREATE TEMPORARY TABLE articles_scored_temp
                ON COMMIT DROP
                AS SELECT main_assistant_article_keywords.article_id, SUM(keywords_sorted_temp.weight) as value
                FROM main_assistant_article_keywords, keywords_sorted_temp
                WHERE main_assistant_article_keywords.keyword_id = keywords_sorted_temp.id
                GROUP BY main_assistant_article_keywords.article_id
                ORDER BY value DESC;
                SELECT main_assistant_article.*, grouped_articles.value as value
                FROM main_assistant_article, (SELECT * FROM articles_scored_temp
                                              WHERE value > %s * (SELECT value
                                                                  FROM articles_scored_temp
                                                                  LIMIT 1)) AS grouped_articles
                WHERE main_assistant_article.id = grouped_articles.article_id;
            '''.format(format_str), arguments)
            return results

    return search


def tf_art_search_plpy(max_keywords=MAX_KEYWORDS):
    def search(text):
        keywords = extract_keywords(text, max_keywords)
        encoded_arg = json.dumps(keywords)
        results = Article.objects.raw('''
            SELECT * FROM boolean_article_search(%s);
        ''', [encoded_arg])
        return results

    return search


def tf_art_search_naive(max_keywords=MAX_KEYWORDS):
    def search(text):
        keywords = extract_keywords(text, max_keywords)
        results = OrderedDict()

        def add_article(article, weight):
            if article.identifier in results:
                results[article.identifier].value += weight
            else:
                results[article.identifier] = article
                article.value = weight

        for keyword_name, occurence_count in keywords.items():
            for article in Article.objects.filter(keywords__keyword=keyword_name):
                add_article(article, occurence_count)
        results = sorted(results.values(), key=lambda x: x.value, reverse=True)
        return results

    return search


def tf_art_search_naive_plpy(max_keywords=MAX_KEYWORDS):
    def search(text):
        keywords = extract_keywords(text, max_keywords)
        encoded_arg = json.dumps(keywords)
        results = Article.objects.raw('''
            SELECT * FROM boolean_article_search_naive(%s);
        ''', [encoded_arg])
        return results

    return search


def tf_idf_pub_search(max_keywords=MAX_KEYWORDS, score_threshold=SCORE_THRESHOLD):
    def search(text):
        keywords = extract_keywords(text)
        arguments = [(key, value) for key, value in keywords.items()]
        format_str = ','.join(('%s' for _ in range(len(arguments))))
        arguments.append(max_keywords)
        arguments.append(score_threshold)
        # using approximate total document count
        # see: https://wiki.postgresql.org/wiki/Count_estimate
        with transaction.atomic():
            results = Publication.objects.raw('''
                CREATE TEMPORARY TABLE keywords_input_temp (
                    keyword varchar(255) not null,
                    occurs integer not null
                ) ON COMMIT DROP;
                INSERT INTO keywords_input_temp VALUES
                {};
                CREATE TEMPORARY TABLE keywords_sorted_temp
                ON COMMIT DROP
                AS SELECT main_assistant_keyword.*, (LOG((SELECT reltuples AS article_count
                                                          FROM pg_class
                                                          WHERE relname = 'main_assistant_article')
                                                       / main_assistant_keyword.occurrence_count) + 1)
                                                    * sqrt(keywords_input_temp.occurs) AS weight
                FROM main_assistant_keyword, keywords_input_temp
                WHERE keywords_input_temp.keyword = main_assistant_keyword.keyword
                ORDER BY weight DESC LIMIT %s;
                CREATE TEMPORARY TABLE articles_scored_temp
                ON COMMIT DROP
                AS SELECT main_assistant_article_keywords.article_id, SUM(keywords_sorted_temp.weight) as value
                FROM main_assistant_article_keywords, keywords_sorted_temp
                WHERE main_assistant_article_keywords.keyword_id = keywords_sorted_temp.id
                GROUP BY main_assistant_article_keywords.article_id
                ORDER BY value DESC;
                SELECT main_assistant_publication.*, SUM(grouped_articles.value) as value
                FROM main_assistant_publication, main_assistant_article,
                (SELECT * FROM articles_scored_temp
                 WHERE value > %s * (SELECT value
                                     FROM articles_scored_temp
                                     LIMIT 1)) AS grouped_articles
                WHERE main_assistant_article.id = grouped_articles.article_id
                AND main_assistant_article.publication_id = main_assistant_publication.id
                GROUP BY main_assistant_publication.id
                ORDER BY value DESC;
            '''.format(format_str), arguments)
            return results

    return search


def tf_pub_search(max_keywords=MAX_KEYWORDS, score_threshold=SCORE_THRESHOLD):
    def search(text):
        keywords = extract_keywords(text)
        arguments = [(key, value) for key, value in keywords.items()]
        format_str = ','.join(('%s' for _ in range(len(arguments))))
        arguments.append(max_keywords)
        arguments.append(score_threshold)
        # using approximate total document count
        # see: https://wiki.postgresql.org/wiki/Count_estimate
        with transaction.atomic():
            results = Publication.objects.raw('''
                CREATE TEMPORARY TABLE keywords_input_temp (
                    keyword varchar(255) not null,
                    occurs integer not null
                ) ON COMMIT DROP;
                INSERT INTO keywords_input_temp VALUES
                {};
                CREATE TEMPORARY TABLE keywords_sorted_temp
                ON COMMIT DROP
                AS SELECT main_assistant_keyword.*, keywords_input_temp.occurs AS weight
                FROM main_assistant_keyword, keywords_input_temp
                WHERE keywords_input_temp.keyword = main_assistant_keyword.keyword
                ORDER BY weight DESC LIMIT %s;
                CREATE TEMPORARY TABLE articles_scored_temp
                ON COMMIT DROP
                AS SELECT main_assistant_article_keywords.article_id, SUM(keywords_sorted_temp.weight) as value
                FROM main_assistant_article_keywords, keywords_sorted_temp
                WHERE main_assistant_article_keywords.keyword_id = keywords_sorted_temp.id
                GROUP BY main_assistant_article_keywords.article_id
                ORDER BY value DESC;
                SELECT main_assistant_publication.*, SUM(grouped_articles.value) as value
                FROM main_assistant_publication, main_assistant_article,
                (SELECT * FROM articles_scored_temp
                 WHERE value > %s * (SELECT value
                                     FROM articles_scored_temp
                                     LIMIT 1)) AS grouped_articles
                WHERE main_assistant_article.id = grouped_articles.article_id
                AND main_assistant_article.publication_id = main_assistant_publication.id
                GROUP BY main_assistant_publication.id
                ORDER BY value DESC;
            '''.format(format_str), arguments)
            return results

    return search


def tf_pub_search_plpy(max_keywords=MAX_KEYWORDS):
    def search(text):
        keywords = extract_keywords(text, max_keywords)
        encoded_arg = json.dumps(keywords)
        results = Publication.objects.raw('''
            SELECT * FROM boolean_publication_search(%s);
        ''', [encoded_arg])
        return results

    return search


def tf_pub_search_naive(max_keywords=MAX_KEYWORDS):
    def search(text):
        articles_alg = tf_art_search_naive(max_keywords)
        articles = articles_alg(text)
        results = OrderedDict()

        def handle_article(article):
            if article.publication.identifier in results:
                results[article.publication.identifier].value += article.value
            else:
                results[article.publication.identifier] = article.publication
                results[article.publication.identifier].value = article.value

        for article in articles:
            handle_article(article)
        publications = sorted(results.values(), key=lambda x: x.value, reverse=True)
        return publications

    return search


def tf_pub_search_naive_plpy(max_keywords=MAX_KEYWORDS):
    def search(text):
        keywords = extract_keywords(text, max_keywords)
        encoded_arg = json.dumps(keywords)
        results = Publication.objects.raw('''
            SELECT * FROM boolean_publication_search_naive(%s);
        ''', [encoded_arg])
        return results

    return search


class RawESQuery:
    MAX_SIZE = 10000

    def __init__(self, query, *, postprocess=None):
        self._query = query
        self._results = None
        self._start = None
        self._size = None
        self._postprocess = postprocess

    def __deepcopy__(self, memo):
        clone = self.__class__({})
        for k, v in self.__dict__.items():
            if k == '_results':
                clone.__dict__[k] = None
            else:
                clone.__dict__[k] = copy.deepcopy(v, memo)
        return clone

    def __getitem__(self, item):
        if isinstance(item, slice):
            if item.start is not None:
                start = item.start
            else:
                start = 0
            if item.stop is not None:
                if item.stop <= item.start:
                    return []
                size = item.stop - item.start
            else:
                size = self.MAX_SIZE
            cloned = copy.deepcopy(self)
            cloned._start = start
            cloned._size = size
            return list(cloned)[::item.step] if item.step else cloned
        else:
            assert isinstance(item, int), 'Value must be of int or slice type'
            if self._results is None:
                if self._start is None or self._size is None:
                    self._start = item
                    self._size = 1
                self._evaluate()
                return self._results[0]
            else:
                return self._results[item]

    def __len__(self):
        if self._results is None:
            self._evaluate()
        return len(self._results)

    def __iter__(self):
        if self._results is None:
            self._evaluate()
        return iter(self._results)

    def _evaluate(self):
        if self._start is None or self._size is None:
            self._start = 0
            self._size = self.MAX_SIZE
        self._query['from'] = self._start
        self._query['size'] = self._size
        backend = connections['default'].get_backend()
        try:
            raw_results = backend.conn.search(body=self._query,
                                              index=backend.index_name,
                                              doc_type='modelresult',
                                              _source=True)
            processed_results = backend._process_results(raw_results)
            self._hits = processed_results['hits']
            if self._postprocess is not None and callable(self._postprocess):
                self._results = self._postprocess(processed_results)
        except elasticsearch.TransportError as e:
            backend.log.error("Failed to query Elasticsearch using custom query: %s", e, exc_info=True)
            raise e

    def hits(self):
        if self._results is None:
            self._evaluate()
        return self._hits

    @staticmethod
    def load_all(processed_results, select_related=None):
        def _load_model_objects(model, pks):
            try:
                conn = connections['default']
                ui = conn.get_unified_index()
                index = ui.get_index(model)
                objects = index.read_queryset(using=conn)
                if select_related is not None:
                    objects = objects.select_related(*select_related)
                return objects.in_bulk(pks)
            except NotHandled:
                logger.warning("Model '%s' not handled by the routers.", model)
                # Revert to old behaviour
                if select_related is not None:
                    return model._default_manager.select_related(*select_related).in_bulk(pks)
                else:
                    return model._default_manager.in_bulk(pks)

        results = processed_results['results']
        postprocessed = []
        models_pks = {}
        loaded_objects = {}
        # Remember the search position for each result so we don't have to resort later.
        for result in results:
            models_pks.setdefault(result.model, []).append(result.pk)
        # Load the objects for each model in turn.
        for model in models_pks:
            loaded_objects[model] = _load_model_objects(model, models_pks[model])
        for result in results:
            # We have to deal with integer keys being cast from strings
            model_objects = loaded_objects.get(result.model, {})
            if result.pk not in model_objects:
                try:
                    result.pk = int(result.pk)
                except ValueError:
                    logger.warning('result.pk is not an int:', exc_info=True)
                    pass
            try:
                result._object = model_objects[result.pk]
            except KeyError:
                # logger.warning('No such pk in model_objects:', exc_info=True)
                continue
            postprocessed.append(result)
        processed_results['results'] = postprocessed
        return processed_results


MIN_TERM_FREQ = 2
MAX_QUERY_TERMS = 25
MIN_WORD_LENGTH = 4
MIN_DOC_FREQ = 4
MAX_HANDLED_ARTICLES = 1000


def mlt_art_search(max_query_terms=MAX_QUERY_TERMS, min_term_freq=MIN_TERM_FREQ,
                   min_word_length=MIN_WORD_LENGTH, min_doc_freq=MIN_DOC_FREQ,
                   *, fetch_publications=False):
    def search(text):
        query = {
            'query': {
                'filtered': {
                    'query': {
                        'more_like_this': {
                            'like_text': text,
                            'max_query_terms': max_query_terms,
                            'min_term_freq': min_term_freq,
                            'min_word_length': min_word_length,
                            'min_doc_freq': min_doc_freq,
                        }
                    },
                    'filter': {
                        'term': {
                            DJANGO_CT: get_model_ct(Article)
                        }
                    }
                }
            }
        }

        def postprocess(processed_results):
            if fetch_publications:
                search_results = RawESQuery.load_all(processed_results)
            else:
                search_results = RawESQuery.load_all(processed_results, select_related=['publication'])
            for search_result in search_results['results']:
                search_result.object.value = search_result.score
            return [search_result.object for search_result in search_results['results']]

        return RawESQuery(query, postprocess=postprocess)

    return search


def mlt_pub_search(*args, max_handled_articles=MAX_HANDLED_ARTICLES):
    def search(text):
        articles_search = mlt_art_search(*args, fetch_publications=True)
        articles = articles_search(text)
        if max_handled_articles > 0:
            articles = articles[0:max_handled_articles]
        results = OrderedDict()

        def handle_article(article):
            if article.publication is not None:
                if article.publication.identifier in results:
                    results[article.publication.identifier].value += article.value
                else:
                    results[article.publication.identifier] = article.publication
                    results[article.publication.identifier].value = article.value

        for article in articles:
            handle_article(article)
        publications = sorted(results.values(), key=lambda x: x.value, reverse=True)
        return publications

    return search


def suggest_articles(text, algorithm=mlt_art_search()):
    return algorithm(text)


def suggest_publications(text, algorithm=mlt_pub_search()):
    return algorithm(text)
