import re

from haystack import indexes

from main_assistant.models import Article, Keyword, Author, Publication


class ArticleIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)

    def prepare_text(self, obj):
        if re.search(r'^([a-f0-9]+)$', obj.identifier):
            res = obj.identifier + '\n'
        else:
            res = ''
        res += self.text.prepare_template(obj)
        return res

    def get_model(self):
        return Article

    def index_queryset(self, using=None):
        return self.get_model().objects.all()


class AuthorIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.NgramField(document=True, model_attr='full_name')

    def get_model(self):
        return Author

    def index_queryset(self, using=None):
        return self.get_model().objects.all()


class KeywordIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.NgramField(document=True, model_attr='keyword')

    def get_model(self):
        return Keyword

    def index_queryset(self, using=None):
        return self.get_model().objects.qualified_keywords()


class PublicationIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    name = indexes.NgramField(model_attr='name')
    is_journal = indexes.BooleanField(model_attr='is_journal')

    def get_model(self):
        return Publication

    def index_queryset(self, using=None):
        return self.get_model().objects.all()
