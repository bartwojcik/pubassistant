from django.db import models
from django.db.models.functions import Length

from .utils import convert, ChoiceEnum


class DigitalLibrary(models.Model):
    name = models.CharField(max_length=50, unique=True)
    total_articles = models.IntegerField()
    enabled = models.BooleanField(default=False)

    @property
    def processed_block_articles(self):
        return convert(DownloadBlock.objects.filter(library=self).aggregate(sum=models.Sum('size'))['sum'], int,
                       default=0)
        # blocks = DownloadBlock.objects.filter(library=self).order_by('-start')
        # return blocks[0].start + blocks[0].size if len(blocks) > 0 else 0

    @property
    def sorted_blocks(self):
        return DownloadBlock.objects.filter(library=self).order_by('start')

    class Meta:
        verbose_name_plural = "Digital libraries"


class DownloadBlock(models.Model):
    start = models.IntegerField()
    size = models.IntegerField()
    library = models.ForeignKey(DigitalLibrary, related_name='blocks')


# a journal or a conference
class Publication(models.Model):
    # ISSN or MD5 Hash of the name if missing
    identifier = models.CharField(max_length=32, unique=True)
    internal_identifier = models.CharField(max_length=255, db_index=True, blank=True)
    name = models.TextField(blank=True)
    location = models.CharField(max_length=2000)
    is_journal = models.BooleanField()
    aim_and_scope = models.TextField(blank=True)
    digital_library = models.ForeignKey(DigitalLibrary, related_name='publications')

    def __str__(self):
        return '{}({})'.format(self.name, self.identifier)


class RankingType(ChoiceEnum):
    impact_factor = 0
    mnisw_points = 1
    eigenfactor = 2


class Ranking(models.Model):
    journal = models.ForeignKey(Publication, related_name='rankings')
    type = models.CharField(max_length=1, choices=RankingType.choices())
    value = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    date = models.DateField()


class Author(models.Model):
    full_name = models.CharField(max_length=255, db_index=True)


class KeywordManager(models.Manager):
    MIN_REFERENCE_COUNT = 3
    MIN_KEYWORD_LENGTH = 3

    def qualified_keywords_values(self):
        return Keyword.objects.filter(occurrence_count__gte=self.MIN_REFERENCE_COUNT) \
            .annotate(text_len=Length('keyword')).filter(text_len__gte=self.MIN_KEYWORD_LENGTH) \
            .values_list('keyword', flat=True)

    def qualified_keywords(self):
        return Keyword.objects.filter(occurrence_count__gte=self.MIN_REFERENCE_COUNT) \
            .annotate(text_len=Length('keyword')).filter(text_len__gte=self.MIN_KEYWORD_LENGTH)


class Keyword(models.Model):
    keyword = models.CharField(max_length=255, unique=True)
    occurrence_count = models.IntegerField(default=1)
    objects = KeywordManager()

    def __str__(self):
        return self.keyword


class Article(models.Model):
    identifier = models.CharField(max_length=255, unique=True)
    internal_identifier = models.CharField(max_length=255, db_index=True, blank=True)
    title = models.TextField()
    location = models.CharField(max_length=2000)
    abstract = models.TextField(blank=True)  # as surprising as it may seem...
    issue_date = models.DateField(blank=True, null=True)
    publication = models.ForeignKey(Publication, related_name='articles', blank=True, null=True)
    authors = models.ManyToManyField(Author)
    keywords = models.ManyToManyField(Keyword)
    references = models.ManyToManyField('self', through='Reference', symmetrical=False, related_name='is_referred')


class Reference(models.Model):
    # TODO django does not support multi-column primary key
    # https://code.djangoproject.com/wiki/MultipleColumnPrimaryKeys
    # pk on both columns and index on second column would suffice, something like this:
    # referring = models.ForeignKey(Article, related_name='out_references')
    # referred = models.ForeignKey(Article, related_name='in_references', db_index=True)
    # https://stackoverflow.com/questions/4714607/how-to-properly-index-a-many-many-association-table
    # https://stackoverflow.com/questions/17614025/does-columns-order-in-multiple-columns-unique-constraint-make-any-difference-is
    #
    # class Meta():
    #     pk_together = ['referring', 'referred']
    # instead, we have a useless, redundant pk, and one index more
    # the only question is if to use single or multi-column indexes
    referring = models.ForeignKey(Article, related_name='out_references', db_index=True)
    referred = models.ForeignKey(Article, related_name='in_references', db_index=True)

    class Meta():
        unique_together = ('referring', 'referred')
        # index_together = [
        #     ['referring', 'referred'],
        #     ['referred', 'referring']
        # ]


class SavedReference(models.Model):
    referring = models.ForeignKey(Article, related_name='out_saved_references')
    referred_location = models.CharField(max_length=2000, db_index=True)
    referred_location_is_internal_identifier = models.BooleanField(default=False)

    class Meta():
        unique_together = ('referring', 'referred_location')
