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
        # Check if ffprobe path is absolute, otherwise assume it's in PATH
        executable = ffprobe_path if Path(ffprobe_path).is_absolute() else 'ffprobe'
        
        result = subprocess.run(
            [executable, *command[1:]],
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        duration = float(result.stdout.strip())
        logger.info(f"Video duration detected: {duration} seconds.")
        return duration
    except subprocess.CalledProcessError as e:
        logger.error(f"FFprobe failed to get duration for {video_path}. Error: {e.stderr}")
        return 0.0
    except FileNotFoundError:
        logger.critical(f"FFprobe not found at '{ffprobe_path}' or in PATH.")
        return 0.0
    except Exception as e:
        logger.error(f"Error getting video duration: {e}", exc_info=True)
        return 0.0

def generate_clip_timestamps(video_path, params, ffprobe_path):
    """Generates clip start/end timestamps based on auto-split parameters."""
    duration_s = get_video_duration(video_path, ffprobe_path)
    if duration_s <= 0:
        return [], 0
        
    duration_ms = duration_s * 1000
    clips = []
    
    if params['mode'] == 'duration':
        split_duration_ms = params['value'] * 1000
        start_ms = 0
        while start_ms < duration_ms:
            end_ms = min(start_ms + split_duration_ms, duration_ms)
            clips.append({'start': start_ms, 'end': end_ms})
            start_ms = end_ms # Move to the next start time
            
    elif params['mode'] == 'number':
        num_clips = params['value']
        if num_clips > 0:
            clip_length_ms = duration_ms / num_clips
            for i in range(num_clips):
                start_ms = i * clip_length_ms
                end_ms = min((i + 1) * clip_length_ms, duration_ms)
                # Ensure we don't create extremely short clips at the end due to float issues
                if end_ms - start_ms > 10: # Minimum 10ms length
                    clips.append({'start': start_ms, 'end': end_ms})
                    
    return clips, duration_s

def get_output_filename(base_path, original_filename, clip_index, start_ms, end_ms, suffix="clip"):
    """
    Generates a unique, descriptive output filename for the clip.
    Example: 720_clip_01_00-00-05_to_00-00-10.mp4
    """
    original_name = Path(original_filename).stem
    original_ext = Path(original_filename).suffix
    
    # Format time strings for the filename
    # We use a cleaner format for filenames (m-s-ms)
    def format_time(ms):
        s, ms_rem = divmod(int(ms), 1000)
        m, s = divmod(s, 60)
        return f"{m:02d}-{s:02d}.{int(ms_rem/10):02d}" # M-S.MS
    
    start_time_str = format_time(start_ms).replace('.', '_')
    end_time_str = format_time(end_ms).replace('.', '_')
    
    # Simple and clear filename format: OriginalName_Clip_Index_StartTime_to_EndTime.ext
    filename = f"{original_name}_{suffix}_{clip_index:02d}_{start_time_str}_to_{end_time_str}{original_ext}"
    
    # Ensure filename is safe 
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    return str(Path(base_path) / filename)


def get_ffmpeg_split_commands(video_path, clips, output_folder, ffprobe_path, ffmpeg_path, config):
    """
    Generates the list of FFmpeg command dictionaries required for splitting.
    
    Returns:
    A list of dictionaries, where each dict has:
    - 'command': The full list of command arguments (to be executed by subprocess.run).
    - 'output_path': The final expected path of the output file.
    """
    commands_list = []
    
    # Ensure output directory exists
    ensure_folder(output_folder)
    
    # Get original filename for naming convention
    original_filename = Path(video_path).name
    
    # FFmpeg execution path (used in the command list)
    ffmpeg_executable = ffmpeg_path if Path(ffmpeg_path).is_absolute() else 'ffmpeg'
    
    # Determine encoding settings (using copy for fastest processing)
    codec = config.get('ffmpeg_settings', {}).get('codec', 'copy') 
    
    for i, clip in enumerate(clips):
        start_time_str = ms_to_ffmpeg_time(clip['start'])
        duration_ms = clip['end'] - clip['start']
        
        if duration_ms <= 0:
            logger.warning(f"Skipping clip {i+1}: duration is zero or negative.")
            continue
            
        duration_time_str = ms_to_ffmpeg_time(duration_ms)
        
        # 1. Generate the required output path (Crucial for the fix)
        output_path = get_output_filename(
            base_path=output_folder,
            original_filename=original_filename,
            clip_index=i + 1,
            start_ms=clip['start'],
            end_ms=clip['end']
        )
        
        # 2. Build the FFmpeg command
        # Use input seeking (-ss before -i) for speed and duration (-to)
        command = [
            ffmpeg_executable,
            '-ss', start_time_str,      # Seek to start position
            '-i', video_path,           # Input file
            '-to', duration_time_str,   # Duration (or end time)
        ]
        
        if codec == 'copy':
            command.extend(['-c', 'copy']) # Fast, lossless copy of streams
        else:
            # Placeholder for re-encoding logic if needed
            command.extend([
                '-c:v', 'libx264',
                '-crf', '23',
                '-c:a', 'aac'
            ])

        # Final output path and necessary flags
        command.extend([
            '-avoid_negative_ts', 'make_zero',
            '-y', # Overwrite output files without asking
            output_path
        ])
        
        # 3. Return the necessary dictionary structure (KeyError fix)
        commands_list.append({
            'command': command,
            'output_path': output_path
        })
        
    return commands_list