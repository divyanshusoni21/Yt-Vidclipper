import os

from django.http import  FileResponse
from django.db import transaction
from django.conf import settings
from yt_helper.settings import logger
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import ClipRequest,STATUS_CHOICES
from .tasks import get_task_status
from .serializers import ClipRequestSerializer
from .services import VideoInfoService, HybridProcessingService

from utility.functions import runSerializer
import django_rq
import traceback
from threading import Thread



class ClipRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing clip requests with full CRUD operations
    Follows established patterns with proper error handling and logging
    """
    queryset = ClipRequest.objects.all()
    serializer_class = ClipRequestSerializer




    def get_serializer_context(self):
        """
        Add field exclusion context for different actions
        """
        context = super().get_serializer_context()
        
        # Exclude sensitive fields in list view
        if self.action == 'list':
            context['exclude_fields'] = ['processing_log', 'error_message']
        
        return context

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a new clip request using runSerializer with transaction management
        """
        try:
            logger.info(f"Creating new clip request with data: {request.data}")
            
            youtubeUrl = request.data.get('youtube_url')
            startTime = request.data.get('start_time')
            endTime = request.data.get('end_time')

            # Validate YouTube URL and get video info
            isValidYoutubeUrl = VideoInfoService().validateYoutubeUrl(youtubeUrl)

            if not isValidYoutubeUrl:
                raise Exception(f"Invalid YouTube URL: {youtubeUrl}")

            # TODO # Validate timestamp range against video duration
            # if clipRequest.end_time > videoInfo.get('duration', 0):
            #     raise Exception(f"End time {clipRequest.end_time} exceeds video duration {videoInfo.get('duration', 0)}")
            
            # create clip request
            clipRequest, serializer = runSerializer(
                ClipRequestSerializer, 
                request.data, 
                request=request
            )
            
            try:
                
                # Queue background processing task
                # queue = django_rq.get_queue('default')
                # rqJob = queue.enqueue(HybridProcessingService().process_clip_request, clipRequest)
                
                # jobId = rqJob.id
                # logger.info(f"Queued background processing for clip request {clipRequest.id}, job ID: {jobId}")
                
                # # Add job_id to response for tracking
                # clipRequest.rq_job_id = jobId
                # clipRequest.save(update_fields=['rq_job_id'])

                thread = Thread(target=HybridProcessingService().process_clip_request, args=(clipRequest,))
                thread.start()
                responseData = ClipRequestSerializer(clipRequest,context={'request': request}).data
                
                return Response(responseData, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                clipRequest.status = STATUS_CHOICES[2][0] # failed
                clipRequest.error_message = str(e)
                clipRequest.save(update_fields=['status', 'error_message'])
                raise Exception(e)

        except Exception as e:
            logger.error(traceback.format_exc())
            
            return Response({
                'error': 'Failed to create clip request',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def task_status(self, request, pk=None):
        """
        Get background task status for a clip request
        """
        try:
            clipRequestId = request.query_params.get('clip_request_id')
            if not clipRequestId:
                raise Exception('clip_request_id parameter is required')
            

            clipRequest = ClipRequest.objects.get(id=clipRequestId)
            if not clipRequest:
                raise Exception(f"Clip request not found: {clipRequestId}")

            serializer = ClipRequestSerializer(clipRequest,context={'request': request})
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response({
                'error': 'Failed to get task status',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class DownloadClipViewSet(viewsets.ViewSet):
    """
    ViewSet for secure file download with proper headers
    Handles clip file serving with validation and error handling
    """
    permission_classes = [AllowAny]

    def retrieve(self, request, pk=None):
        """
        Download clip file by clip request ID
        """
        try:
            logger.info(f"Download request for clip {pk}")
            
            # Get the clip request
            try:
                clipRequest = ClipRequest.objects.get(id=pk)
            except ClipRequest.DoesNotExist:
                logger.warning(f"Clip request not found: {pk}")
                return Response({
                    'error': 'Clip request not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if clip is completed
            if clipRequest.status != 'completed':
                logger.warning(f"Clip {pk} is not ready for download. Status: {clipRequest.status}")
                return Response({
                    'error': f'Clip is not ready for download. Current status: {clipRequest.status}',
                    'status': clipRequest.status
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if file path exists
            if not clipRequest.file_path:
                logger.error(f"No file path found for completed clip {pk}")
                return Response({
                    'error': 'File path not found for this clip'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Construct full file path
            full_file_path = os.path.join(settings.MEDIA_ROOT, clipRequest.file_path)
            
            # Validate file existence
            if not os.path.exists(full_file_path):
                logger.error(f"File not found on disk: {full_file_path}")
                return Response({
                    'error': 'Clip file not found on server'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Validate file size
            try:
                file_size = os.path.getsize(full_file_path)
                if file_size == 0:
                    logger.error(f"Empty file found: {full_file_path}")
                    return Response({
                        'error': 'Clip file is empty'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except OSError as e:
                logger.error(f"Error accessing file {full_file_path}: {str(e)}")
                return Response({
                    'error': 'Error accessing clip file'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Generate appropriate filename
            filename = self._generate_download_filename(clipRequest)
            
            try:
                # Create file response with proper headers
                response = FileResponse(
                    open(full_file_path, 'rb'),
                    content_type='video/mp4',
                    as_attachment=True,
                    filename=filename
                )
                
                # Add additional security headers
                response['Content-Length'] = file_size
                response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
                
                # Add CORS headers if needed
                response['Access-Control-Allow-Origin'] = '*'
                response['Access-Control-Expose-Headers'] = 'Content-Disposition'
                
                logger.info(f"Successfully serving file {filename} for clip {pk}")
                
                # TODO: Uncomment when ready for analytics
                # Record download in analytics if available
                # try:
                #     analytics = clipRequest.analytics.first()
                #     if analytics:
                #         analytics.download_count = getattr(analytics, 'download_count', 0) + 1
                #         analytics.last_downloaded_at = timezone.now()
                #         analytics.save(update_fields=['download_count', 'last_downloaded_at'])
                # except Exception as analytics_error:
                #     logger.warning(f"Failed to record download analytics: {str(analytics_error)}")
                
                return response
                
            except IOError as e:
                logger.error(f"Error reading file {full_file_path}: {str(e)}")
                return Response({
                    'error': 'Error reading clip file'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Download failed for clip {pk}: {str(e)}")
            return Response({
                'error': 'Download failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
