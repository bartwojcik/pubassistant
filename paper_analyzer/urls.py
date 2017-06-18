from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^search_publications$', views.search_publications, name='search_publications'),
    url(r'^publication_rankings', views.get_rankings, name='get_rankings'),
    url(r'^search_articles$', views.search_articles, name='search_articles'),
    url(r'^article_partial$', views.article_partial, name='article_partial'),
    url(r'^article_text_partial$', views.article_text_partial, name='article_text_partial'),
    url(r'^article_results_partial$', views.article_results_partial, name='article_results_partial'),
    url(r'^article_journals_partial$', views.journal_results_partial, name='journal_results_partial'),
]