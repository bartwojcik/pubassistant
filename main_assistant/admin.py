from django.contrib import admin

from .models import DigitalLibrary
from .tasks import update_articles


@admin.register(DigitalLibrary)
class DigitalLibraryAdmin(admin.ModelAdmin):
    fields = ('name', 'enabled',)
    readonly_fields = ('name',)
    list_display = ('name', 'enabled',)
    actions = ('force_update',)

    def force_update(self, request, queryset):
        selected_dls = [dl for dl in queryset]
        names = [dl.name for dl in selected_dls]
        update_articles.delay(names)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
