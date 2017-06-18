import logging

from django.db.models import Count
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from author_browser.serializers import CoreferrerResultsSerializer
from author_browser.services import search_authors, find_coreferrers
from main_assistant.models import Author, Article
from main_assistant.serializers import ArticleSerializer, AuthorSerializer
from main_assistant.utils import RangeHeaderPaginator

logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 10


def author_partial(request):
    return render(request, 'author_browser/author_partial.html')


def author_details_partial(request):
    return render(request, 'author_browser/author_details_partial.html')


@api_view(['GET'])
def author_search(request):
    id_param = request.query_params.get('id')
    submitted_name = request.query_params.get('query')
    if submitted_name is None and id_param is None:
        return Response('query or id parameter missing', status=status.HTTP_400_BAD_REQUEST)
    elif submitted_name is not None and id_param is not None:
        return Response('query and id cannot be both present', status=status.HTTP_400_BAD_REQUEST)
    elif submitted_name is None:
        try:
            id = int(id_param)
        except (ValueError, TypeError):
            return Response('id parameter not int type', status=status.HTTP_400_BAD_REQUEST)
        return Response(AuthorSerializer(Author.objects.get(pk=id)).data)
    elif id_param is None:
        return RangeHeaderPaginator(search_authors(submitted_name), AuthorSerializer).get_response(request)


@api_view(['GET'])
def author_articles(request):
    id_param = request.query_params.get('id')
    if id_param is None:
        return Response('id parameter missing', status=status.HTTP_400_BAD_REQUEST)
    else:
        try:
            id = int(id_param)
        except (ValueError, TypeError):
            return Response('id parameter not int type', status=status.HTTP_400_BAD_REQUEST)
    sort = request.query_params.get('sort')
    if sort is not None and sort == 'citations':
        qs = Article.objects.filter(authors__pk=id).annotate(cited=Count('is_referred')).order_by('cited')
    else:
        qs = Article.objects.filter(authors__pk=id).order_by('title')
    return RangeHeaderPaginator(qs, ArticleSerializer).get_response(request)


@api_view(['GET'])
def author_coreferrers(request):
    id_param = request.query_params.get('id')
    if id_param is None:
        return Response('id parameter missing', status=status.HTTP_400_BAD_REQUEST)
    else:
        try:
            id = int(id_param)
        except (ValueError, TypeError):
            return Response('id parameter not int type', status=status.HTTP_400_BAD_REQUEST)
    author = Author.objects.get(pk=id)
    coreferrers = find_coreferrers(author)
    return Response(CoreferrerResultsSerializer(coreferrers, many=True).data)
