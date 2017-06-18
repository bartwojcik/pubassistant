# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2016-09-10 16:03
from __future__ import unicode_literals

import django.contrib.postgres.operations
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_assistant', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='keyword',
            name='occurrence_count',
            field=models.IntegerField(default=1),
        ),
        migrations.RunSQL(
            sql='\n            UPDATE main_assistant_keyword keyword_t\n            SET occurrence_count = helper_table.count\n            FROM (SELECT relation_t.keyword_id as id, COUNT(relation_t.article_id) as count\n                                   FROM main_assistant_article_keywords relation_t\n                                   GROUP BY relation_t.keyword_id) helper_table\n            WHERE helper_table.id = keyword_t.id;\n        ',
            reverse_sql='',
        ),
    ]