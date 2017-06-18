from rest_framework import serializers

from main_assistant.serializers import AuthorSerializer, ArticleSerializer


class ReferenceResultSerializer(serializers.Serializer):
    referring = ArticleSerializer()
    referred = ArticleSerializer()


class CoreferrerResultsSerializer(serializers.Serializer):
    author = AuthorSerializer()
    references = ReferenceResultSerializer(many=True)
    backreferences = ReferenceResultSerializer(many=True)
