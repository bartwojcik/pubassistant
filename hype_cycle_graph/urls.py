from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^keyword_search$', views.keyword_search, name='keyword_search'),
    url(r'^publication_search$', views.publication_search, name='publication_search'),
    url(r'^graph_data$', views.graph_data, name='graph_data'),
    url(r'^graph_partial$', views.graph_partial, name='graph_partial'),
]