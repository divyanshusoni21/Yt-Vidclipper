import re
import yt_dlp
import os
import subprocess
import time
from typing import Dict, Any

from django.conf import settings
from django.utils import timezone

from .models import STATUS_CHOICES
import shutil
from time import time
from utility.functions import time_to_seconds
import traceback
from yt_helper.settings import logger
from django_rq import job


class VideoNotAvailableException(Exception):
    """Exception raised when a video is not available or accessible."""
    pass


class InvalidUrlException(Exception):
    """Exception raised when a YouTube URL is invalid."""
    pass


class ProcessingFailedException(Exception):
    """Exception raised when video processing fails."""
    pass


class VideoInfoService:
    """Service class for handling YouTube video information extraction."""
    

    def getVideoInfo(self, url: str, ydlOpts: Dict[str, Any]=None) -> Dict[str, Any]:
        """
        Extract comprehensive video information using yt-dlp.
        
        Args:
            url (str): The YouTube URL
            
        Returns:
            Dict[str, Any]: Dictionary containing video information
            
        Raises:
            InvalidUrlException: If the URL is invalid
            VideoNotAvailableException: If the video is not accessible
        """
        if not self.validateYoutubeUrl(url):
            raise InvalidUrlException(f"Invalid YouTube URL: {url}")
        
        ydlOpts = ydlOpts or self.ydl_opts
            
        try:
            with yt_dlp.YoutubeDL(ydlOpts) as ydl:
                logger.info(f"Extracting video info for URL: {url}")
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise VideoNotAvailableException(f"No information available for video: {url}")
                
                # Extract relevant information
                video_info = {
                    'title': info.get('title'),
                    'channel': info.get('channel'),
                    'channel_id': info.get('channel_id'),
                    'url': info.get('url'),
                }
                
                # Log successful extraction
                logger.info(f"Successfully extracted info for video: {video_info['title']}")
                
                return video_info
                
        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            logger.error(f"yt-dlp download error for URL {url}: {error_msg}")
            
            # Handle specific error cases
            if 'private video' in error_msg.lower():
                raise VideoNotAvailableException(f"Video is private: {url}")
            elif 'video unavailable' in error_msg.lower():
                raise VideoNotAvailableException(f"Video is unavailable: {url}")
            elif 'age-restricted' in error_msg.lower():
                raise VideoNotAvailableException(f"Video is age-restricted: {url}")
            elif 'copyright' in error_msg.lower():
                raise VideoNotAvailableException(f"Video has copyright restrictions: {url}")
            elif 'geo-blocked' in error_msg.lower() or 'not available in your country' in error_msg.lower():
                raise VideoNotAvailableException(f"Video is geo-blocked: {url}")
            else:
                raise VideoNotAvailableException(f"Video not accessible: {error_msg}")
                
        except Exception as e:
            logger.error(f"Unexpected error extracting video info for URL {url}: {str(e)}")
            raise VideoNotAvailableException(f"Failed to extract video information: {str(e)}")
    

class ClipProcessingService:
    """Service class for processing video clips using hybrid methods."""
    
    # 10-minute threshold for processing method selection (in seconds)
    DURATION_THRESHOLD = 600

        # YouTube URL patterns for validation
    YOUTUBE_URL_PATTERNS = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    
    def validate_youtube_url(self,url: str) -> bool:
        """
        Validate if the provided URL is a valid YouTube URL.
        
        Args:
            url (str): The YouTube URL to validate
            
        Returns:
            bool: True if valid YouTube URL, False otherwise
        """
        if not url or not isinstance(url, str):
            return False
            
        # Check against all YouTube URL patterns
        for pattern in self.YOUTUBE_URL_PATTERNS:
            if re.match(pattern, url.strip()):
                return True
                
        return False
    
    
    def __init__(self):
        """Initialize the HybridProcessingService."""
        self.videoInfoService = VideoInfoService()
        self.base_ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        # Ensure ffmpeg is installed
        self._check_ffmpeg()
    
    
    def _check_ffmpeg(self):
        """Checks if ffmpeg is installed and in the system's PATH."""
        if not shutil.which("ffmpeg"):
            raise FileNotFoundError(
                "ffmpeg is not installed or not in your system's PATH. "
                "Please install ffmpeg to use this script."
            )

    def ffmpeg_stream_download(self, clipRequest,directStreamUrl) -> bool:
        """
            Decouples downloading from processing for maximum stability.
            Step 1: Download 720p clip (Direct Stream Copy) - Network Bound
            Step 2: Generate 480p from local 720p file - CPU Bound
            
            Args:
                clipRequest: ClipRequest model instance
        """
        try:
            t1 = time()
            self.log_processing_step(
                clipRequest,
                'method_ffmpeg_stream',
                'info',
                {'message': 'Starting Method : FFmpeg Stream Processing'}
            )
            
            # Create directory for this request
            request_dir = os.path.join('media','clips', str(clipRequest.id))
            os.makedirs(request_dir, exist_ok=True)
            
            # Prepare output filename
            out720pPath = f"720p.mp4"
            out480pPath = f"480p.mp4"

            # Absolute paths for file operations (ffmpeg)
            out720pPathAbsolute = os.path.join(request_dir, out720pPath)
            out480pPathAbsolute = os.path.join(request_dir, out480pPath)
            
            # Relative paths for Django FileField (relative to MEDIA_ROOT)
            out720pPathRelative = os.path.join('clips', str(clipRequest.id), out720pPath)
            out480pPathRelative = os.path.join('clips', str(clipRequest.id), out480pPath)

            startSec = time_to_seconds(str(clipRequest.start_time))
            endSec = time_to_seconds(str(clipRequest.end_time))
            
            clipDuration = endSec - startSec

            # when start time is 0, the clip is most likely to be distorted. 
            # so as of now a quick fix
            if startSec == 0 :
                startSec = 1
          
            # Use FFmpeg to seek and download only the required segment
            ffmpegCmd720p = [
                'ffmpeg',
                '-ss', str(startSec),  # Seek to start time
                '-i', directStreamUrl,
                '-t', str(clipDuration),  # Duration of clip
                
                
                # # Output 1: 720p (Source is max 720p, so we just re-encode or scale if needed)
                # # We use scale=-2:720 to ensure it fits 720 height while keeping aspect ratio
                # '-map', '0:v', '-map', '0:a',
                # '-vf', 'scale=-2:720', 
                # '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                # '-c:a', 'aac',
                # '-avoid_negative_ts', 'make_zero',
                # '-y', out_720,

                # Output 1: 720p (Source is 720p, so we COPY for speed)
                # Note: We use -c copy instead of re-encoding. 
                # This is much faster but relies on the source keyframes.
                '-map', '0:v', '-map', '0:a',
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                '-y', out720pPathAbsolute,
            ]
                        
            try:
                result = subprocess.run(
                    ffmpegCmd720p, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            except subprocess.TimeoutExpired as e:
                errorMsg = f"FFmpeg 720p processing timed out after 300 seconds"
                logger.error(errorMsg)
                raise ProcessingFailedException(errorMsg)
            except subprocess.CalledProcessError as e:
                errorMsg = f"FFmpeg 720p processing failed: {e.stderr if e.stderr else str(e)}"
                logger.error(errorMsg)
                raise ProcessingFailedException(errorMsg)
            
            logger.info(f"FFmpeg 720p processing completed successfully")
            
            # Verify output file exists and has content
            if not os.path.exists(out720pPathAbsolute) or os.path.getsize(out720pPathAbsolute) == 0:
                raise ProcessingFailedException("Output clip file is empty or missing")
            
            t2 = time()
            self.log_processing_step(
                clipRequest,
                'download_720p_clip',
                'info',
                {'message': f'Time taken to download 720p clip: {t2 - t1}s'}
            )
         
            # --- Phase 2: Generate 480p from Local File ---
            t3 = time()
            
            ffmpegCmd480p = [
                'ffmpeg',
                '-i', out720pPathAbsolute,
                '-vf', 'scale=-2:480',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac',
                '-y', out480pPathAbsolute
            ]
            
            try:
                result = subprocess.run(
                    ffmpegCmd480p, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            except subprocess.TimeoutExpired as e:
                raise ProcessingFailedException("FFmpeg 480p processing timed out after 300 seconds")
            except subprocess.CalledProcessError as e:
                raise ProcessingFailedException(f"FFmpeg 480p processing failed: {e.stderr if e.stderr else str(e)}")
            
            # Verify output file exists and has content
            if not os.path.exists(out480pPathAbsolute) or os.path.getsize(out480pPathAbsolute) == 0:
                raise ProcessingFailedException("Output clip file is empty or missing")
            
            t4 = time()
            self.log_processing_step(
                clipRequest,
                'generate_480p_clip',
                'info',
                {'message': f'Time taken to generate 480p clip: {t4 - t3}s'}
            )
             
            # Update clip request with file info
            clipRequest.clip_720p = out720pPathRelative
            clipRequest.clip_480p = out480pPathRelative
            clipRequest.clip_720p_size = os.path.getsize(out720pPathAbsolute)
            clipRequest.clip_480p_size = os.path.getsize(out480pPathAbsolute)
            clipRequest.save(update_fields=['clip_720p', 'clip_480p', 'clip_720p_size', 'clip_480p_size'])
            
            return True
            
        except Exception as e:
            logger.error(traceback.format_exc())
            self.log_processing_step(
                clipRequest,
                'method_c_error',
                'error',
                {'error': str(e), 'exception_type': type(e).__name__}
            )
            return False
    
    @job('default', timeout='5m')
    def process_clip_request(self, clipRequest) -> bool:
        """
        Process a clip request using the appropriate hybrid method.
        
        Args:
            clipRequest: ClipRequest model instance
            
        Returns:
            bool: True if processing successful, False otherwise
        """
        try:
            t1 = time()
            # Log processing start
            self.log_processing_step(
                clipRequest, 
                'processing_start', 
                'info', 
                {'message': 'Starting clip processing'}
            )
                
            # Get video info of youtube url
            ydlOpts = {
                **self.base_ydl_opts,
                'format': 'best[height<=720]',
            }
            
            with yt_dlp.YoutubeDL(ydlOpts) as ydl:
                videoInfo = ydl.extract_info(clipRequest.youtube_url, download=False)

                if not videoInfo or 'url' not in videoInfo:
                    raise ProcessingFailedException("Could not extract streaming URL")
                
                # Check if end time is greater than video duration

                duration = videoInfo.get('duration',0)
                endSec = time_to_seconds(str(clipRequest.end_time))
                if endSec > duration:
                    # set end time to video duration
                    endSec = videoInfo.get('duration_string')
                    clipRequest.end_time = endSec
                    
                
                directStreamUrl = videoInfo.get('url')
                clipRequest.original_title = videoInfo.get('title')
                clipRequest.channel_name = videoInfo.get('channel')
                clipRequest.channel_id = videoInfo.get('channel_id')
                clipRequest.clip_duration = videoInfo.get('duration')

                clipRequest.save(update_fields=['original_title', 'channel_name', 'channel_id', 'clip_duration','end_time'])
            
            t2 = time()

            self.log_processing_step(
                clipRequest,
                'get_video_info',
                'info',
                {'message': f'Got video info in {t2 - t1}s'}
            )

            success = self.ffmpeg_stream_download(clipRequest,directStreamUrl)

            t3 = time()
            logger.info(f"Total time taken to process clip: {t3 - t1}s")

            # Update final status
            if success:
                clipRequest.status = STATUS_CHOICES[1][0] # completed
                clipRequest.processed_at = timezone.now()
                self.log_processing_step(
                    clipRequest,
                    'processing_complete',
                    'success',
                    {'message': f'Clip processing completed successfully, time taken: {t3 - t1}s'}
                )
            else:
                clipRequest.status = STATUS_CHOICES[2][0] # failed
                self.log_processing_step(
                    clipRequest,
                    'processing_failed',
                    'error',
                    {'message': 'All processing methods failed'}
                )
            
            clipRequest.total_time_taken = t3 - t1
            clipRequest.save(update_fields=['status', 'processed_at', 'total_time_taken'])
            return success

        except Exception as e:
            logger.error(traceback.format_exc())
            clipRequest.status = STATUS_CHOICES[2][0] # failed
            clipRequest.error_message = str(e)
            clipRequest.save(update_fields=['status', 'error_message'])

            
            self.log_processing_step(
                clipRequest,
                'processing_error',
                'error',
                {'error': str(e), 'exception_type': type(e).__name__}
            )
            
            return False
    
 
    
    def methodA_downloadAndClip(self, clipRequest) -> bool:
        """
        Method A: Download full video and clip using FFmpeg.
        Used for videos under 10 minutes.
        
        Args:
            clipRequest: ClipRequest model instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.log_processing_step(
                clipRequest,
                'method_a_start',
                'info',
                {'message': 'Starting Method A: Download and Clip'}
            )
            
            # Create directories for this request
            media_root = getattr(settings, 'MEDIA_ROOT', 'media')
            request_dir = os.path.join(media_root, 'clips', str(clipRequest.id))
            temp_dir = os.path.join(media_root, 'temp', str(clipRequest.id))
            os.makedirs(request_dir, exist_ok=True)
            os.makedirs(temp_dir, exist_ok=True)
            
            # Download full video
            temp_video_path = os.path.join(temp_dir, 'full_video.%(ext)s')
            ydl_opts = {
                **self.base_ydl_opts,
                'outtmpl': temp_video_path,
                'format': 'best[height<=1080]',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.log_processing_step(
                    clipRequest,
                    'method_a_download',
                    'info',
                    {'message': 'Downloading full video'}
                )
                
                ydl.download([clipRequest.youtube_url])
            
            # Find the downloaded file (yt-dlp adds extension)
            downloadedFiles = [f for f in os.listdir(temp_dir) if f.startswith('full_video.')]
            if not downloadedFiles:
                raise ProcessingFailedException("Downloaded video file not found")
            
            downloadedVideo = os.path.join(temp_dir, downloadedFiles[0])
            
            # Clip the video using FFmpeg
            output_filename = f"clip_{clipRequest.start_time}_{clipRequest.end_time}.mp4"
            output_path = os.path.join(request_dir, output_filename)
            
            clip_duration = clipRequest.end_time - clipRequest.start_time
            
            ffmpegCmd = [
                'ffmpeg',
                '-i', downloadedVideo,
                '-ss', str(clipRequest.start_time),
                '-t', str(clip_duration),
                '-c', 'copy',  # Copy streams without re-encoding for speed
                '-avoid_negative_ts', 'make_zero',
                '-y',  # Overwrite output file
                output_path
            ]
            
            self.log_processing_step(
                clipRequest,
                'method_a_clip',
                'info',
                {
                    'message': 'Clipping video with FFmpeg',
                    'start_time': clipRequest.start_time,
                    'duration': clip_duration,
                    'command': ' '.join(ffmpegCmd)
                }
            )
            
            result = subprocess.run(ffmpegCmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise ProcessingFailedException(f"FFmpeg failed: {result.stderr}")
            
            # Verify output file exists and has content
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise ProcessingFailedException("Output clip file is empty or missing")
            
            # Update clip request with file info
            clipRequest.file_path = os.path.relpath(output_path, getattr(settings, 'MEDIA_ROOT', 'media'))
            clipRequest.file_size = os.path.getsize(output_path)
            clipRequest.save()
            
            # Clean up temporary files
            try:
                os.remove(downloadedVideo)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temp files for request {clipRequest.id}: {str(e)}")
            
            self.log_processing_step(
                clipRequest,
                'method_a_success',
                'success',
                {
                    'message': 'Method A completed successfully',
                    'file_size': clipRequest.file_size,
                    'output_path': clipRequest.file_path
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Method A failed for request {clipRequest.id}: {str(e)}")
            self.log_processing_step(
                clipRequest,
                'method_a_error',
                'error',
                {'error': str(e), 'exception_type': type(e).__name__}
            )
            return False
    
    def methodB_downloadSections(self, clipRequest) -> bool:
        """
        Method B: Download specific sections using yt-dlp --download-sections.
        Used for videos over 10 minutes.
        
        Args:
            clipRequest: ClipRequest model instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.log_processing_step(
                clipRequest,
                'method_b_start',
                'info',
                {'message': 'Starting Method B: Download Sections'}
            )
            
            # Create directory for this request
            media_root = getattr(settings, 'MEDIA_ROOT', 'media')
            request_dir = os.path.join(media_root, 'clips', str(clipRequest.id))
            os.makedirs(request_dir, exist_ok=True)
            
            # Prepare output filename
            output_filename = f"clip_{clipRequest.start_time}_{clipRequest.end_time}.mp4"
            output_path = os.path.join(request_dir, output_filename)
            
            # Format section for yt-dlp (start_time-end_time)
            section = f"{clipRequest.start_time}-{clipRequest.end_time}"
            
            ydl_opts = {
                **self.base_ydl_opts,
                'outtmpl': output_path.replace('.mp4', '.%(ext)s'),
                'format': 'best[height<=1080]',
                'download_sections': section,
            }
            
            self.log_processing_step(
                clipRequest,
                'method_b_download',
                'info',
                {
                    'message': 'Downloading video section',
                    'section': section,
                    'start_time': clipRequest.start_time,
                    'end_time': clipRequest.end_time
                }
            )
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([clipRequest.youtube_url])
            
            # Find the downloaded file (yt-dlp might add different extension)
            downloaded_files = [f for f in os.listdir(request_dir) if f.startswith(f"clip_{clipRequest.start_time}_{clipRequest.end_time}.")]
            if not downloaded_files:
                raise ProcessingFailedException("Downloaded section file not found")
            
            actual_output = os.path.join(request_dir, downloaded_files[0])
            
            # If the file doesn't have .mp4 extension, rename it
            if not actual_output.endswith('.mp4'):
                os.rename(actual_output, output_path)
                actual_output = output_path
            
            # Verify output file exists and has content
            if not os.path.exists(actual_output) or os.path.getsize(actual_output) == 0:
                raise ProcessingFailedException("Output clip file is empty or missing")
            
            # Update clip request with file info
            clipRequest.file_path = os.path.relpath(actual_output, getattr(settings, 'MEDIA_ROOT', 'media'))
            clipRequest.file_size = os.path.getsize(actual_output)
            clipRequest.save()
            
            self.log_processing_step(
                clipRequest,
                'method_b_success',
                'success',
                {
                    'message': 'Method B completed successfully',
                    'file_size': clipRequest.file_size,
                    'output_path': clipRequest.file_path
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Method B failed for request {clipRequest.id}: {str(e)}")
            self.log_processing_step(
                clipRequest,
                'method_b_error',
                'error',
                {'error': str(e), 'exception_type': type(e).__name__}
            )
            return False
    

    def log_processing_step(self, clipRequest, step: str, status: str, details: dict) -> None:
        """
        Log a processing step to the clip request's processing log.
        
        Args:
            clipRequest: ClipRequest model instance
            step (str): The processing step identifier
            status (str): Status of the step ('info', 'warning', 'error', 'success')
            details (dict): Additional details about the step
        """
        try:
            # Ensure processing_log is a dict
            if not isinstance(clipRequest.processing_log, dict):
                clipRequest.processing_log = {}
            
            # Create log entry
            log_entry = {
                'timestamp': timezone.now().isoformat(),
                'step': step,
                'status': status,
                'details': details
            }
            
            # Add to processing log
            if 'steps' not in clipRequest.processing_log:
                clipRequest.processing_log['steps'] = []
            
            clipRequest.processing_log['steps'].append(log_entry)
            
            # Save the updated log
            clipRequest.save(update_fields=['processing_log'])
            
            # Also log to Django logger
            log_message = f"ClipRequest {clipRequest.id} - {step}: {details.get('message', str(details))}"
            if status == 'error':
                logger.error(log_message)
            elif status == 'warning':
                logger.warning(log_message)
            elif status == 'success':
                logger.info(f"SUCCESS: {log_message}")
            else:
                logger.info(log_message)
                
        except Exception as e:
            logger.error(f"Failed to log processing step for request {clipRequest.id}: {str(e)}")


