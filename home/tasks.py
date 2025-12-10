"""
Background tasks for YouTube clipper processing using Django-RQ.
"""
import os
import logging
from django.conf import settings
from django_rq import job
from rq import get_current_job
from .models import ClipRequest
from .services import HybridProcessingService, VideoInfoService

logger = logging.getLogger('django')


@job('default', timeout=600)  # 10 minute timeout for clip processing
def process_clip_task(clipRequestId):
    """
    Background task to process a clip request using HybridProcessingService.
    
    Args:
        clipRequestid (str): UUID of the ClipRequest to process
        
    Returns:
        dict: Processing result with success status and details
    """
    job = get_current_job()
    
    try:
        # Get the clip request
        clipRequest = ClipRequest.objects.get(id=clipRequestId)
        
        # Update status to processing
        clipRequest.status = 'processing'
        clipRequest.save()
        
        # Log processing start
        logger.info(f"Starting clip processing for request {clipRequestId}")
        
        # Update job meta with progress
        if job:
            job.meta['progress'] = 10
            job.meta['status'] = 'Initializing processing'
            job.save_meta()
        
        # Initialize services
        videoInfoRequest = VideoInfoService()
        processingService = HybridProcessingService()
        
        # Get video information first
        try:
            videInfo = videoInfoRequest.getVideoInfo(clipRequest.youtube_url)
            clipRequest.video_duration = videInfo.get('duration', 0)
            clipRequest.original_title = videInfo.get('title', '')
            clipRequest.channel_name = videInfo.get('channel', '')
            clipRequest.channel_id = videInfo.get('channel_id', '')
            clipRequest.save()
            
            if job:
                job.meta['progress'] = 20
                job.meta['status'] = 'Video information retrieved'
                job.save_meta()
                
        except Exception as e:
            logger.error(f"Failed to get video info for {clipRequestId}: {str(e)}")
            clipRequest.error_message = f"Failed to retrieve video information: {str(e)}"
            clipRequest.status = 'failed'
            clipRequest.save()
            
            if job:
                job.meta['progress'] = 0
                job.meta['status'] = 'Failed to retrieve video information'
                job.save_meta()
                
            return {
                'success': False,
                'error': str(e),
                'clip_request_id': clipRequestId
            }
        
        # Process the clip using hybrid processing service
        try:
            if job:
                job.meta['progress'] = 30
                job.meta['status'] = 'Starting clip processing'
                job.save_meta()
            
            # Process the clip
            success = processingService.processClipRequest(clipRequest)
            
            if success:
                clipRequest.status = 'completed'
                clipRequest.save()
                
                if job:
                    job.meta['progress'] = 100
                    job.meta['status'] = 'Clip processing completed successfully'
                    job.save_meta()
                
                logger.info(f"Successfully processed clip for request {clipRequestId}")
                
                # Schedule cleanup task for later
                cleanup_temp_files.delay(clipRequestId, delay=3600)  # Cleanup after 1 hour
                
                return {
                    'success': True,
                    'clip_request_id': clipRequestId,
                    'file_path': clipRequest.file_path,
                    'file_size': clipRequest.file_size
                }
            else:
                clipRequest.status = 'failed'
                clipRequest.save()
                
                if job:
                    job.meta['progress'] = 0
                    job.meta['status'] = 'Clip processing failed'
                    job.save_meta()
                
                logger.error(f"Failed to process clip for request {clipRequestId}")
                
                return {
                    'success': False,
                    'error': clipRequest.error_message or 'Processing failed',
                    'clip_request_id': clipRequestId
                }
                
        except Exception as e:
            logger.error(f"Exception during clip processing for {clipRequestId}: {str(e)}")
            clipRequest.error_message = str(e)
            clipRequest.status = 'failed'
            clipRequest.save()
            
            if job:
                job.meta['progress'] = 0
                job.meta['status'] = f'Processing failed: {str(e)}'
                job.save_meta()
            
            return {
                'success': False,
                'error': str(e),
                'clip_request_id': clipRequestId
            }
            
    except ClipRequest.DoesNotExist:
        error_msg = f"ClipRequest with id {clipRequestId} not found"
        logger.error(error_msg)
        
        if job:
            job.meta['progress'] = 0
            job.meta['status'] = 'Clip request not found'
            job.save_meta()
        
        return {
            'success': False,
            'error': error_msg,
            'clip_request_id': clipRequestId
        }
    
    except Exception as e:
        error_msg = f"Unexpected error processing clip {clipRequestId}: {str(e)}"
        logger.error(error_msg)
        
        if job:
            job.meta['progress'] = 0
            job.meta['status'] = f'Unexpected error: {str(e)}'
            job.save_meta()
        
        return {
            'success': False,
            'error': error_msg,
            'clip_request_id': clipRequestId
        }


@job('low', timeout=300)  # 5 minute timeout for cleanup tasks
def cleanup_temp_files(clip_request_id, delay=0):
    """
    Background task to cleanup temporary files after processing completion.
    
    Args:
        clip_request_id (str): UUID of the ClipRequest to cleanup
        delay (int): Delay in seconds before cleanup (default: 0)
    """
    import time
    
    if delay > 0:
        time.sleep(delay)
    
    try:
        clip_request = ClipRequest.objects.get(id=clip_request_id)
        
        # Define temp directory for this request
        temp_dir = os.path.join(settings.TEMP_STORAGE_ROOT, str(clip_request_id))
        
        if os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary files for request {clip_request_id}")
        
        # Update processing log
        if hasattr(clip_request, 'processing_log') and clip_request.processing_log:
            clip_request.processing_log['cleanup_completed'] = True
            clip_request.save()
            
    except ClipRequest.DoesNotExist:
        logger.warning(f"ClipRequest {clip_request_id} not found during cleanup")
    except Exception as e:
        logger.error(f"Error during cleanup for {clip_request_id}: {str(e)}")


@job('low', timeout=600)  # 10 minute timeout for bulk cleanup
def cleanup_old_files():
    """
    Background task to cleanup old clip files and temporary files based on retention settings.
    This should be run periodically (e.g., via cron job or scheduled task).
    """
    from datetime import datetime, timedelta
    import shutil
    
    try:
        # Calculate cutoff times
        clip_cutoff = datetime.now() - timedelta(hours=settings.CLIP_RETENTION_HOURS)
        temp_cutoff = datetime.now() - timedelta(hours=settings.TEMP_FILE_RETENTION_HOURS)
        
        # Cleanup old completed clips
        old_clips = ClipRequest.objects.filter(
            status='completed',
            processed_at__lt=clip_cutoff
        )
        
        clips_cleaned = 0
        for clip in old_clips:
            if clip.file_path and os.path.exists(clip.file_path):
                try:
                    os.remove(clip.file_path)
                    clips_cleaned += 1
                    logger.info(f"Removed old clip file: {clip.file_path}")
                except Exception as e:
                    logger.error(f"Failed to remove clip file {clip.file_path}: {str(e)}")
        
        # Cleanup old temporary directories
        temp_dirs_cleaned = 0
        if os.path.exists(settings.TEMP_STORAGE_ROOT):
            for item in os.listdir(settings.TEMP_STORAGE_ROOT):
                item_path = os.path.join(settings.TEMP_STORAGE_ROOT, item)
                if os.path.isdir(item_path):
                    # Check if directory is old enough
                    dir_mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                    if dir_mtime < temp_cutoff:
                        try:
                            shutil.rmtree(item_path)
                            temp_dirs_cleaned += 1
                            logger.info(f"Removed old temp directory: {item_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove temp directory {item_path}: {str(e)}")
        
        logger.info(f"Cleanup completed: {clips_cleaned} clip files, {temp_dirs_cleaned} temp directories removed")
        
        return {
            'success': True,
            'clips_cleaned': clips_cleaned,
            'temp_dirs_cleaned': temp_dirs_cleaned
        }
        
    except Exception as e:
        logger.error(f"Error during bulk cleanup: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def get_task_status(job_id):
    """
    Get the status of a background task.
    
    Args:
        job_id (str): The job ID returned when task was queued
        
    Returns:
        dict: Task status information
    """
    from django_rq import get_connection
    from rq.job import Job
    
    try:
        redis_conn = get_connection('default')
        job = Job.fetch(job_id, connection=redis_conn)
        
        if job.is_finished:
            return {
                'status': 'completed',
                'result': job.result,
                'progress': 100
            }
        elif job.is_failed:
            return {
                'status': 'failed',
                'error': str(job.exc_info),
                'progress': 0
            }
        elif job.is_started:
            progress = job.meta.get('progress', 0) if job.meta else 0
            status_msg = job.meta.get('status', 'Processing') if job.meta else 'Processing'
            return {
                'status': 'processing',
                'progress': progress,
                'message': status_msg
            }
        else:
            return {
                'status': 'queued',
                'progress': 0,
                'message': 'Task is queued for processing'
            }
            
    except Exception as e:
        logger.error(f"Error getting task status for job {job_id}: {str(e)}")
        return {
            'status': 'unknown',
            'error': str(e),
            'progress': 0
        }


def queue_clip_processing(clip_request):
    """
    Queue a clip request for background processing.
    
    Args:
        clip_request (ClipRequest): The clip request to process
        
    Returns:
        str: Job ID for tracking the task
    """
    try:
        job = process_clip_task.delay(str(clip_request.id))
        logger.info(f"Queued clip processing task for request {clip_request.id}, job ID: {job.id}")
        return job.id
    except Exception as e:
        logger.error(f"Failed to queue clip processing for request {clip_request.id}: {str(e)}")
        raise