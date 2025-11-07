# modules/video_processor.py

import subprocess
import os
import re
import logging
from pathlib import Path
import math

logger = logging.getLogger("BlackNode-Clipper.VideoProcessor")

def ms_to_ffmpeg_time(ms):
    """Converts milliseconds to FFmpeg's required HH:MM:SS.mmm format."""
    if ms < 0: ms = 0
    s, ms_rem = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    # FFmpeg time format H:M:S.millisecond
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"

def ensure_folder(path):
    """Creates a directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)

def get_video_duration(video_path, ffprobe_path):
    """Uses ffprobe to get the video duration in seconds."""
    command = [
        ffprobe_path,
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    
    try:
        # Check if ffprobe exists before running
        subprocess.run([ffprobe_path, '-version'], check=True, capture_output=True)
        
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        duration = float(result.stdout.strip())
        return duration
    except FileNotFoundError:
        logger.error(f"FFprobe executable not found at {ffprobe_path}. Please check config.yaml or PATH.")
        return 0
    except subprocess.CalledProcessError as e:
        logger.error(f"FFprobe execution failed: {e.stderr}", exc_info=True)
        return 0
    except Exception as e:
        logger.error(f"An unexpected error occurred during ffprobe execution: {e}", exc_info=True)
        return 0

def generate_clip_timestamps(video_path, params, ffprobe_path):
    # ... (unchanged logic) ...
    # ... (function body remains the same) ...
    duration_sec = get_video_duration(video_path, ffprobe_path)
    if duration_sec <= 0:
        raise Exception("Could not determine video duration.")

    duration_ms = duration_sec * 1000
    
    clips = []
    
    if params['mode'] == 'duration':
        segment_ms = params['value'] * 1000
        start = 0
        while start < duration_ms:
            end = min(start + segment_ms, duration_ms)
            clips.append({'start': int(start), 'end': int(end)})
            start = end
            
    elif params['mode'] == 'number':
        num_clips = params['value']
        if num_clips > 0:
            segment_ms = duration_ms / num_clips
            for i in range(num_clips):
                start = i * segment_ms
                end = min((i + 1) * segment_ms, duration_ms)
                clips.append({'start': int(start), 'end': int(end)})

    return clips, duration_ms

# UPDATED: Added 'extension' argument
def get_output_filename(base_path, original_filename, clip_index, start_ms, end_ms, extension):
    """Generates a unique, timestamped output filename with the correct extension."""
    
    # 1. Sanitize the original filename for safety
    base_name = re.sub(r'[^\w\-_\.]', '_', Path(original_filename).stem)
    
    # Format timestamps for clarity
    start_str = ms_to_ffmpeg_time(start_ms).replace(':', '-').replace('.', '_')
    end_str = ms_to_ffmpeg_time(end_ms).replace(':', '-').replace('.', '_')
    
    # 2. Append clip details and correct extension
    output_filename = f"{base_name}_clip_{clip_index:02d}_{start_str}_{end_str}.{extension}"
    
    # 3. Build the full path
    output_path = Path(base_path) / output_filename
    return str(output_path)

# UPDATED: Replaced individual codec parameters with 'format_data' dict
def get_ffmpeg_split_commands(video_path, output_folder, clips, ffmpeg_executable, format_data):
    """
    Generates a list of FFmpeg commands to split the video based on clip data and format settings.
    """
    if not clips:
        return []

    original_filename = Path(video_path).name # Get full name including extension
    
    # Extract format-specific data
    extension = format_data['extension']
    vcodec = format_data['video_codec']
    acodec = format_data['audio_codec']
    options = format_data.get('options', [])
    
    commands = []
    
    for i, clip in enumerate(clips):
        # Calculate start and duration
        start_time_str = ms_to_ffmpeg_time(clip['start'])
        duration_ms = clip['end'] - clip['start']
        duration_time_str = ms_to_ffmpeg_time(duration_ms)
        
        # 1. Generate the required output path
        output_path = get_output_filename(
            base_path=output_folder,
            original_filename=original_filename,
            clip_index=i + 1,
            start_ms=clip['start'],
            end_ms=clip['end'],
            extension=extension # Pass the dynamic extension
        )
        
        # 2. Build the FFmpeg command
        command = [
            ffmpeg_executable,
            '-ss', start_time_str,      # Seek to start position
            '-i', video_path,           # Input file
            '-to', duration_time_str,   # Duration (or end time)
        ]
        
        # Add format-specific codecs and options
        if vcodec == 'copy' and acodec == 'copy':
            command.extend(['-c', 'copy']) # Fast, lossless copy of streams
        else:
            # Video codec
            command.extend(['-c:v', vcodec])
            
            # Audio codec
            if acodec == 'an': # No audio
                command.extend(['-an'])
            else:
                command.extend(['-c:a', acodec])
                
            # Additional options (e.g., CRF, bitrate, pixel format)
            command.extend(options)

        # Final output path and necessary flags
        command.extend([
            '-avoid_negative_ts', 'make_zero',
            '-y', # Overwrite output files without asking
            output_path
        ])
        
        # 3. Return the necessary dictionary structure
        commands.append({'command': command, 'output_file': output_path})
        
    return commands