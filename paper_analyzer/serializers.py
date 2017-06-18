from rest_framework import serializers

from main_assistant.models import Article, Publication, Ranking


class ArticleResultSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = ('id', 'identifier', 'title', 'location', 'abstract', 'issue_date', 'publication', 'score')

    def get_score(self, obj):
        return obj.value


class JournalResultSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = Publication
        fields = ('id', 'identifier', 'name', 'location', 'is_journal', 'aim_and_scope', 'score')

    def get_score(self, obj):
        return obj.value


class RankingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ranking
        fields = ('type', 'value', 'date')
