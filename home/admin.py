from django.contrib import admin
from .models import ClipRequest

# Register your models here.
@admin.register(ClipRequest)
class ClipRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'youtube_url', 'start_time', 'end_time', 'status', 'created_at', 'updated_at']
    list_filter = ['status', ]
    search_fields = ['id','youtube_url', 'original_title', 'channel_name']
    ordering = ['-created_at']
    list_per_page = 10
    list_max_show_all = 100
    list_display_links = ['id', 'youtube_url']
    # list_select_related = ['channel']