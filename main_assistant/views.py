from django.http import HttpResponse
from django.shortcuts import render

from main_assistant.models import Article, Publication, Keyword, Author, Reference, SavedReference
from main_assistant.services import url_providers_map


def index(request):
    return render(request, 'main_assistant/index.html')


def status(request):
    response_str = ''
    for provider in url_providers_map.values():
        processed, total = provider.download_status()
        response_str += '<p>' + provider.__name__ + ' has downloaded ' + str(processed) + '/' + str(total) + '</p>'
    response_str += '<hr/>'
    response_str += '<p> {} articles in database </p>'.format(Article.objects.count())
    response_str += '<p> {} publications in database </p>'.format(Publication.objects.count())
    response_str += '<p> {} keywords in database </p>'.format(Keyword.objects.count())
    response_str += '<p> {} authors in database </p>'.format(Author.objects.count())
    response_str += '<p> {} references in database </p>'.format(Reference.objects.count())
    response_str += '<p> {} saved references in database </p>'.format(SavedReference.objects.count())
    return HttpResponse(response_str)
