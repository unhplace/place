from django.contrib import admin
from ogp.models import BoundedItem, Category, DownloadRequest, ItemCollection

# Register your models here.
admin.site.register(BoundedItem)
admin.site.register(Category)
admin.site.register(ItemCollection)
admin.site.register(DownloadRequest)
