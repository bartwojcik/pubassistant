import logging

from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response

from main_assistant.serializers import KeywordSerializer, PublicationSerializer
from hype_cycle_graph.services import search_keywords, get_hype_graph_data, search_publications

logger = logging.getLogger(__name__)


@api_view(['GET'])
def graph_data(request, format=None):
    if request.method == 'GET':
        keyword_id = request.query_params.get('keyword')
        publication_ids = request.query_params.get('publications')
        if publication_ids:
            publication_ids = publication_ids.split(',')
        data = get_hype_graph_data(keyword_id, publication_ids)
        return Response(data)


@api_view(['GET'])
def keyword_search(request, format=None):
    if request.method == 'GET':
        query_text = request.query_params.get('query')
        keywords = search_keywords(query_text)
        return Response(KeywordSerializer(keywords, many=True).data)


@api_view(['GET'])
def publication_search(request, format=None):
    if request.method == 'GET':
        query_text = request.query_params.get('query')
        publications = search_publications(query_text)
        return Response(PublicationSerializer(publications, many=True).data)


def graph_partial(request):
    return render(request, 'hype_cycle_graph/graph_partial.html')
