import csv
import glob
import os
import time
from math import exp

from django.db import transaction

from main_assistant.models import Article

PAGE_SIZE = 10
TEST_DATA_DIR = 'test_data'
TEST_RESULTS_DIR = 'test_results'
if not os.path.exists(TEST_RESULTS_DIR):
    os.makedirs(TEST_RESULTS_DIR)
DEFAULT_A = 0.025
DEFAULT_B = 10


# Snippets useful to carry out the tests or find article text:
# from paper_analyzer.tests import *; from paper_analyzer.services import *; build_automaton();
# test_full_text(tf_idf_pub_search(), tf_idf_art_search(), 'tf_idf')
# test_full_text(tf_pub_search(), tf_art_search(), 'tf')
# test_full_text(tf_pub_search_plpy(), tf_art_search_plpy(), 'tf_plpy')
# test_full_text(mlt_pub_search(), mlt_art_search(), 'mlt')
# alg_performance_comparison('term_search_comparison', 5, 75,
#                            (tf_pub_search, tf_art_search),
#                            (tf_pub_search_plpy, tf_art_search_plpy),
#                            (tf_pub_search_naive_plpy, tf_art_search_naive_plpy))
# effectiveness_test('mlt_eff', range(5, 101), mlt_art_search)
# effectiveness_test('tf_idf_eff', range(5, 101), tf_idf_art_search)
# effectiveness_test('tf_eff', range(5, 101), tf_art_search)


# import datetime; from django.db.models import Count; from django.db.models.functions import Length
# y2015 = datetime.date(2015, 1, 1)
# y2014 = datetime.date(2014, 1, 1)
# articles = list(Article.objects.filter(issue_date__lt=y2015).filter(issue_date__gt=y2014)
# .annotate(count=Count('references')).filter(count__gte=20).filter(count__lt=30))
# def describe(article):
#     print('pk: {}'.format(article.pk))
#     print('identifier: {}'.format(article.identifier))
#     print('title: {}'.format(article.title))
#     print('location: {}'.format(article.location))
#     print('references count: {}'.format(article.count))


def get_test_article_pks():
    article_text_dir = '{}/{}'.format(os.path.dirname(os.path.abspath(__file__)), TEST_DATA_DIR)
    article_text_files = [filename for filename in glob.glob('{}/[0-9]*'.format(article_text_dir))]
    article_pks = [int(os.path.splitext(os.path.basename(path))[0]) for path in article_text_files]
    article_pks.sort(key=lambda x: os.path.getsize('{}/{}.txt'.format(article_text_dir, x)))
    return article_pks


def load_text(article_pk):
    article_text_dir = '{}/{}'.format(os.path.dirname(os.path.abspath(__file__)), TEST_DATA_DIR)
    with open('{}/{}.txt'.format(article_text_dir, article_pk)) as f:
        return f.read()


def alg_performance_comparison(test_run_name, min, max, *alg_pairs):
    article_pk = get_test_article_pks()[0]
    x = list(range(min, max + 1))
    article_text = load_text(article_pk)
    with open(TEST_RESULTS_DIR + '/' + test_run_name + '_performance.csv', 'w') as f:
        writer = csv.writer(f)
        labels = ('max_keywords',)
        for pair in alg_pairs:
            labels = labels + (pair[0].__name__, pair[1].__name__)
        print(labels)
        writer.writerow(labels)
        for k in x:
            results = [k]
            for pair in alg_pairs:
                pub_elapsed, pub_mdcg, pub_hit = test_publication_search(article_pk, article_text, pair[0](k),
                                                                         DEFAULT_A, DEFAULT_B)
                ref_count, art_elapsed, art_mdcg, art_nmdcg, arg_hits = test_article_search(article_pk,
                                                                                            article_text,
                                                                                            pair[1](k),
                                                                                            DEFAULT_A, DEFAULT_B)
                results.append(pub_elapsed)
                results.append(art_elapsed)
            writer.writerow(results)
            print(results)
        writer.writerow(('article_pk={};text_size={}'.format(article_pk, len(article_text)),))


def effectiveness_test(test_run_name, x, art_alg):
    article_pks = get_test_article_pks()
    with open(TEST_RESULTS_DIR + '/' + test_run_name + '_effectiveness.csv', 'w') as f:
        writer = csv.writer(f)
        labels = ('max_keywords',
                  art_alg.__name__ + '_avg_time', art_alg.__name__ + '_avg_mdcg', art_alg.__name__ + '_avg_nmdcg',)
        print(labels)
        writer.writerow(labels)
        for k in x:
            results = [k]
            sums = [0, 0, 0]
            for article_pk in article_pks:
                article_text = load_text(article_pk)
                ref_count, art_elapsed, art_mdcg, art_nmdcg, arg_hits = test_article_search(article_pk,
                                                                                            article_text,
                                                                                            art_alg(k),
                                                                                            DEFAULT_A, DEFAULT_B)
                sums[0] += art_elapsed
                sums[1] += art_mdcg
                sums[2] += art_nmdcg
            results.extend((s / len(article_pks) for s in sums))
            writer.writerow(results)
            print(results)


def test_full_text(pub_alg, art_alg, test_run_name, a=DEFAULT_A, b=DEFAULT_B):
    print('=================FULL TEXT=================')
    article_pks = get_test_article_pks()
    with open(TEST_RESULTS_DIR + '/' + test_run_name + '_full_texts.csv', 'w') as f:
        writer = csv.writer(f)
        labels = ('article_pk', 'text_size', 'ref_count', 'pub_elapsed', 'pub_mdcg',
                  'pub_hit', 'art_elapsed', 'art_mdcg', 'art_nmdcg', 'art_hits')
        writer.writerow(labels)
        print(labels)
        sums = [0, 0, 0, 0, 0]
        for article_pk in article_pks:
            article_text = load_text(article_pk)
            pub_elapsed, pub_mdcg, pub_hit = test_publication_search(article_pk,
                                                                     article_text,
                                                                     pub_alg,
                                                                     a, b)
            ref_count, art_elapsed, art_mdcg, art_nmdcg, arg_hits = test_article_search(article_pk,
                                                                                        article_text,
                                                                                        art_alg,
                                                                                        a, b)
            results = (article_pk, len(article_text), ref_count, pub_elapsed, pub_mdcg, pub_hit,
                       art_elapsed, art_mdcg, art_nmdcg, str(arg_hits))
            writer.writerow(results)
            print(results)
            sums[0] += pub_elapsed
            sums[1] += pub_mdcg
            sums[2] += art_elapsed
            sums[3] += art_mdcg
            sums[4] += art_nmdcg
        sums = [s / len(article_pks) for s in sums]
        summary = 'avg_pub_elapsed: {}, avg_pub_mdcg: {},' \
                  ' avg_art_elapsed: {}, avg_art_mdcg: {}, avg_art_nmdcg: {}'.format(*sums)
        print(summary)
        writer.writerow((summary,))


class CancelTransactionError(Exception):
    pass


def modified_discounted_cumulated_gain(score_vector, a, b):
    """Calculate modified discounted cumulated gain vector.

    This is a modified version of DCG ( K. Järvelin, J. Kekäläinen,
    Cumulated gain-based evaluation of ir tech-niques, ACM Trans.
    Inf. Syst. 20 (4) (2002) 422–446.) that adjusts discounting formula to
    fairly calculate gain for low rank hits. That allows us to describe overall
    effectiveness of a method by taking the last value of the (M)DCG vector.

    The discounting formula is:
    exp(-a * (pos - b))

    Good value for a could be 0.025.

    :param score_vector: Score vector. Can be any iterable with real values.
    :param a: a parameter.
    :param b: b parameter (point where discounting begins).
    :return: Modified discounted cumulated gain sum vector.
    """
    current_sum = 0
    mdcg_vector = []
    for i, score in enumerate(score_vector):
        pos = i + 1
        if pos < b:
            current_sum += score
        else:
            current_sum += score * exp(-a * (pos - b))
        mdcg_vector.append(current_sum)
    return mdcg_vector


def test_publication_search(article_pk, article_text, algorithm, a, b):
    mdcg = 0
    elapsed = 0
    hit = -1
    try:
        with transaction.atomic():
            article = Article.objects.select_related('publication').get(pk=article_pk)
            publication = article.publication
            article.delete()
            elapsed = time.perf_counter()
            results = list(algorithm(article_text))
            elapsed = time.perf_counter() - elapsed
            for i, result in enumerate(results):
                if result == publication:
                    hit = i
                    break
            raise CancelTransactionError('rollback')
    except CancelTransactionError:
        pass
    if hit >= 0:
        mdcg = modified_discounted_cumulated_gain((1 if pos == hit else 0 for pos in range(hit + 1)), a, b)[-1]
    return elapsed, mdcg, hit


def test_article_search(article_pk, article_text, algorithm, a, b):
    elapsed = 0
    cited_articles = []
    hits = []
    try:
        with transaction.atomic():
            article = Article.objects.select_related('publication').get(pk=article_pk)
            # references = list(Reference.objects.select_related('referring').filter(referring=article))
            # cited_articles = [reference.referring for reference in references]
            cited_articles = list(article.references.all())
            cited_articles_pks = {article.pk: article for article in cited_articles}
            article.delete()
            elapsed = time.perf_counter()
            results = list(algorithm(article_text))
            elapsed = time.perf_counter() - elapsed
            for i, result in enumerate(results):
                if result.pk in cited_articles_pks:
                    hits.append(i)
            raise CancelTransactionError('rollback')
    except CancelTransactionError:
        pass
    mdcg = modified_discounted_cumulated_gain((1 if pos in hits else 0 for pos in range(hits[-1] + 1)),
                                              a, b)[-1] if hits else 0
    ideal_mdcg = modified_discounted_cumulated_gain((1 for _ in range(len(cited_articles))),
                                                    a, b)[-1]
    nmdcg = 0 if ideal_mdcg == 0 else mdcg / ideal_mdcg
    return len(cited_articles), elapsed, mdcg, nmdcg, hits

# Create your tests here.
