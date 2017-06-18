from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^author_partial$', views.author_partial, name='author_partial'),
    url(r'^author_details_partial$', views.author_details_partial, name='author_details_partial'),
    url(r'^author_search$', views.author_search, name='author_search'),
    url(r'^author_articles$', views.author_articles, name='author_articles'),
    url(r'^author_coreferrers$', views.author_coreferrers, name='author_coreferrers'),
]
