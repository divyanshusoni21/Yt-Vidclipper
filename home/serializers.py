import re
from rest_framework import serializers
from django.core.exceptions import ValidationError
from utility.mixins import FieldMixin
from .models import ClipRequest, ClipAnalytics
from utility.functions import time_to_seconds


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

    def validate(self, data):
        """
        Cross-field validation for timestamp ranges
        """
        startTime = data.get('start_time')
        endTime = data.get('end_time')

        startTime = time_to_seconds(str(startTime))
        endTime = time_to_seconds(str(endTime))
        
        
        if startTime is not None and endTime is not None:
            if endTime <= startTime:
                raise serializers.ValidationError({
                    'endTime': 'End time must be after start time.'
                })
            
            # Check if clip duration is reasonable (not too short or too long)
            clip_duration = endTime - startTime
          
            if clip_duration < 10:
                raise serializers.ValidationError({
                    'endTime': 'Clip duration must be at least 10 second.'
                })
            
            # Maximum clip duration of 30 minutes (1800 seconds)
            if clip_duration > 1800:
                raise serializers.ValidationError({
                    'endTime': 'Clip duration cannot exceed 30 minutes.'
                })
        
        return data
    
    def to_representation(self, instance):
        """
        Customize the serialized representation
        """
        data = super().to_representation(instance)
        
        # # Add computed fields for API responses
        startTime = data.get('start_time')
        endTime = data.get('end_time')

        startTime = time_to_seconds(str(startTime))
        endTime = time_to_seconds(str(endTime))

        clipDuration = endTime - startTime
        data['clip_duration'] = clipDuration
        
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


    