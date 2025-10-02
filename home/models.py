from django.db import models
from utility.mixins import UUIDMixin

# Create your models here.

class ClipRequest(UUIDMixin):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    PROCESSING_METHOD_CHOICES = [
        ('download_and_clip', 'Download Full Video and Clip'),
        ('download_sections', 'Download Specific Sections'),
        ('ffmpeg_stream', 'FFmpeg Stream Processing'),
    ]
    
    youtube_url = models.URLField()
    start_time = models.IntegerField()  # in seconds
    end_time = models.IntegerField()    # in seconds
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    file_path = models.CharField(max_length=500, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    original_title = models.CharField(max_length=200, null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    video_duration = models.IntegerField(null=True, blank=True)  # total video duration in seconds
    channel_name = models.CharField(max_length=200, null=True, blank=True)
    channel_id = models.CharField(max_length=100, null=True, blank=True)
    processing_method = models.CharField(max_length=30, choices=PROCESSING_METHOD_CHOICES, null=True, blank=True)
    processing_log = models.JSONField(default=dict, blank=True)  # Stores detailed processing steps and errors
    
    class Meta:
        db_table = 'clip_request'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"ClipRequest {self.id} - {self.youtube_url} ({self.start_time}-{self.end_time}s)"


class ClipAnalytics(UUIDMixin):
    # Request Analytics
    clip_request = models.ForeignKey(ClipRequest, on_delete=models.CASCADE, related_name='analytics')
    
    # Video Analytics
    video_id = models.CharField(max_length=50)  # YouTube video ID
    video_duration = models.IntegerField()  # in seconds
    clip_duration = models.IntegerField()  # in seconds
    clip_percentage = models.FloatField()  # percentage of original video clipped
    
    # Processing Analytics
    processing_method = models.CharField(max_length=30)
    processing_time = models.FloatField(null=True, blank=True)  # in seconds
    download_size = models.BigIntegerField(null=True, blank=True)  # bytes downloaded
    final_file_size = models.BigIntegerField(null=True, blank=True)  # final clip size
    
    # Channel Analytics
    channel_name = models.CharField(max_length=200, null=True, blank=True)
    channel_id = models.CharField(max_length=100, null=True, blank=True)
    
    # User Behavior Analytics
    user_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    referrer = models.URLField(null=True, blank=True)
    
    # System Performance
    server_load = models.FloatField(null=True, blank=True)
    memory_usage = models.FloatField(null=True, blank=True)  # in MB
    
    # Success/Failure Analytics
    success = models.BooleanField(default=False)
    error_type = models.CharField(max_length=100, null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'clip_analytics'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['video_id']),
            models.Index(fields=['channel_id']),
            models.Index(fields=['processing_method']),
            models.Index(fields=['success']),
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        return f"ClipAnalytics {self.id} - {self.video_id} ({self.processing_method})"
