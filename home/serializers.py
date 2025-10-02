import re
from rest_framework import serializers
from django.core.exceptions import ValidationError
from utility.mixins import FieldMixin
from .models import ClipRequest, ClipAnalytics


class ClipRequestSerializer(FieldMixin, serializers.ModelSerializer):
    """
    Serializer for ClipRequest model with field exclusion capabilities
    and custom validation for timestamp ranges and YouTube URLs
    """
    
    class Meta:
        model = ClipRequest
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'processed_at', 
                           'file_path', 'error_message', 'original_title', 
                           'file_size', 'video_duration', 'channel_name', 
                           'channel_id', 'processing_method', 'processing_log')
    
    def validate_youtube_url(self, value):
        """
        Validate YouTube URL format
        """
        youtube_patterns = [
            r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]+',
            r'^https?://(www\.)?youtu\.be/[\w-]+',
            r'^https?://(www\.)?youtube\.com/embed/[\w-]+',
            r'^https?://(www\.)?youtube\.com/v/[\w-]+',
            r'^https?://m\.youtube\.com/watch\?v=[\w-]+',
        ]
        
        if not any(re.match(pattern, value) for pattern in youtube_patterns):
            raise serializers.ValidationError(
                "Invalid YouTube URL format. Please provide a valid YouTube video URL."
            )
        
        return value
    
    def validate_start_time(self, value):
        """
        Validate start time is non-negative
        """
        if value < 0:
            raise serializers.ValidationError(
                "Start time must be non-negative."
            )
        return value
    
    def validate_end_time(self, value):
        """
        Validate end time is positive
        """
        if value <= 0:
            raise serializers.ValidationError(
                "End time must be positive."
            )
        return value
    
    def validate(self, data):
        """
        Cross-field validation for timestamp ranges
        """
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        
        if start_time is not None and end_time is not None:
            if end_time <= start_time:
                raise serializers.ValidationError({
                    'end_time': 'End time must be after start time.'
                })
            
            # Check if clip duration is reasonable (not too short or too long)
            clip_duration = end_time - start_time
            if clip_duration < 1:
                raise serializers.ValidationError({
                    'end_time': 'Clip duration must be at least 1 second.'
                })
            
            # Maximum clip duration of 30 minutes (1800 seconds)
            if clip_duration > 1800:
                raise serializers.ValidationError({
                    'end_time': 'Clip duration cannot exceed 30 minutes.'
                })
        
        return data
    
    def to_representation(self, instance):
        """
        Customize the serialized representation
        """
        data = super().to_representation(instance)
        
        # Add computed fields for API responses
        if instance.start_time is not None and instance.end_time is not None:
            data['clip_duration'] = instance.end_time - instance.start_time
        
        # Format timestamps for display
        if instance.start_time is not None:
            data['start_time_formatted'] = self._format_seconds_to_time(instance.start_time)
        
        if instance.end_time is not None:
            data['end_time_formatted'] = self._format_seconds_to_time(instance.end_time)
        
        # Add download URL if file is ready
        if instance.status == 'completed' and instance.file_path:
            data['download_url'] = f'/api/clips/{instance.id}/download/'
        
        return data
    
    def _format_seconds_to_time(self, seconds):
        """
        Convert seconds to MM:SS or HH:MM:SS format
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"


class ClipAnalyticsSerializer(FieldMixin, serializers.ModelSerializer):
    """
    Serializer for ClipAnalytics model with computed fields for analytics dashboard
    """
    
    # Computed fields for analytics dashboard
    efficiency_score = serializers.SerializerMethodField()
    processing_speed = serializers.SerializerMethodField()
    compression_ratio = serializers.SerializerMethodField()
    
    class Meta:
        model = ClipAnalytics
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')
    
    def get_efficiency_score(self, obj):
        """
        Calculate efficiency score based on processing time and file size
        """
        if not obj.processing_time or not obj.clip_duration:
            return None
        
        # Efficiency = clip_duration / processing_time (higher is better)
        efficiency = obj.clip_duration / obj.processing_time
        
        # Normalize to 0-100 scale (assuming 1:1 ratio is 50 points)
        score = min(100, efficiency * 50)
        return round(score, 2)
    
    def get_processing_speed(self, obj):
        """
        Calculate processing speed in seconds of video per second of processing
        """
        if not obj.processing_time or not obj.clip_duration:
            return None
        
        speed = obj.clip_duration / obj.processing_time
        return round(speed, 2)
    
    def get_compression_ratio(self, obj):
        """
        Calculate compression ratio if both download and final file sizes are available
        """
        if not obj.download_size or not obj.final_file_size:
            return None
        
        ratio = obj.download_size / obj.final_file_size
        return round(ratio, 2)
    
    def to_representation(self, instance):
        """
        Customize the serialized representation for analytics
        """
        data = super().to_representation(instance)
        
        # Add formatted file sizes
        if instance.download_size:
            data['download_size_mb'] = round(instance.download_size / (1024 * 1024), 2)
        
        if instance.final_file_size:
            data['final_file_size_mb'] = round(instance.final_file_size / (1024 * 1024), 2)
        
        # Add formatted processing time
        if instance.processing_time:
            data['processing_time_formatted'] = self._format_processing_time(instance.processing_time)
        
        # Add success rate context
        data['success_status'] = 'Success' if instance.success else 'Failed'
        
        return data
    
    def _format_processing_time(self, seconds):
        """
        Format processing time for display
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"