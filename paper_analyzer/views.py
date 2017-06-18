import asyncio
import logging

from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from main_assistant.models import Publication
from main_assistant.utils import RangeHeaderPaginator, run_async
from paper_analyzer.serializers import ArticleResultSerializer, JournalResultSerializer, RankingSerializer
from paper_analyzer.services import ranking_source, suggest_publications, suggest_articles

logger = logging.getLogger(__name__)


@api_view(['POST'])
def search_publications(request, format=None):
    if 'text' not in request.data:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    text = request.data['text']
    if not text:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    return RangeHeaderPaginator(suggest_publications(text), JournalResultSerializer).get_response(request)


@api_view(['POST'])
def search_articles(request, format=None):
    if 'text' not in request.data:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    text = request.data['text']
    if not text:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    return RangeHeaderPaginator(suggest_articles(text), ArticleResultSerializer).get_response(request)


@api_view(['GET'])
def get_rankings(request, format=None):
    id = request.query_params.get('id')
    if not id:
        return Response('id query parameter not present', status=status.HTTP_400_BAD_REQUEST)
    journal = Publication.objects.get(pk=id)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    rankings = run_async(ranking_source.get_ranking(journal))
    return Response(RankingSerializer(rankings, many=True).data)


def article_partial(request):
    return render(request, 'paper_analyzer/article_partial.html')


def article_text_partial(request):
    return render(request, 'paper_analyzer/article_text_partial.html')


def article_results_partial(request):
    return render(request, 'paper_analyzer/article_results_partial.html')


def journal_results_partial(request):
    return render(request, 'paper_analyzer/journal_results_partial.html')
