from django.contrib import admin
from .models import Brand


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre', 'descripcion')
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': (
                'nombre',
                'descripcion',
            )
        }),
    )