# modules/workers.py

import subprocess
import os
import logging
from pathlib import Path 
from PySide6.QtCore import QObject, Signal, QProcess

# Only import necessary functions
from .video_processor import get_ffmpeg_split_commands 

logger = logging.getLogger("BlackNode-Clipper.Worker")

class VideoSplitterWorker(QObject):
    """
    Worker class running in a separate QThread to handle the video splitting process (FFmpeg)
    without blocking the UI.
    """
    # CRITICAL FIX: Signals must be defined at the class level (outside __init__)
    finished = Signal(list)    # Sends a list of created file paths
    progress = Signal(int)     # Sends the index of the clip finished
    error = Signal(str)        # Sends an error message if the process fails

    def __init__(self, video_path, output_folder, clips, ffprobe_path, ffmpeg_path, app_config, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.output_folder = output_folder
        self.clips = clips
        self.ffprobe_path = ffprobe_path
        self.ffmpeg_path = ffmpeg_path
        self.app_config = app_config 
        self._is_stopped = False
        self.commands_to_run = []
        
    def stop(self):
        """Requests the splitting process to stop gracefully."""
        self._is_stopped = True
        logger.warning("Splitting process requested to stop.")

    def run(self):
        """
        Executes FFmpeg commands in the separate thread.
        """
        logger.info(f"Worker starting execution for {len(self.clips)} clips.")
        
        created_files = [] 
        
        # 1. Phase 1: Generate FFmpeg commands
        try:
            self.commands_to_run = get_ffmpeg_split_commands( 
                video_path=self.video_path,
                clips=self.clips,
                output_folder=self.output_folder,
                ffprobe_path=self.ffprobe_path,
                ffmpeg_path=self.ffmpeg_path, 
                config=self.app_config 
            )
        except Exception as e:
            error_msg = f"Error during command generation (get_ffmpeg_split_commands): {e}"
            logger.error(error_msg, exc_info=True)
            self.error.emit(error_msg)
            self.finished.emit([]) 
            return 

        # 2. Phase 2: Execute commands sequentially
        for i, cmd_data in enumerate(self.commands_to_run):
            if self._is_stopped:
                logger.warning("Splitting process stopped by user.")
                break
            
            command = cmd_data['command']
            output_file = cmd_data['output_path']
            
            logger.info(f"Executing clip {i+1}/{len(self.commands_to_run)}: {command}")
            
            try:
                
                result = subprocess.run(
                    command,
                    check=True,  
                    capture_output=True,
                    text=True,
                    encoding='utf-8' 
                )
                
                created_files.append(output_file)
                logger.info(f"Successfully split and saved: {output_file}")
                
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg failed for clip {i+1}. Error: {e.stderr}"
                logger.error(error_msg)
                self.error.emit(error_msg)
                break 
            except FileNotFoundError:
                error_msg = f"FFmpeg executable not found. Check if the path is correct in the config or if it is in PATH."
                logger.critical(error_msg)
                self.error.emit(error_msg)
                break
            except Exception as e:
                error_msg = f"An unexpected error occurred during FFmpeg execution: {e}"
                logger.error(error_msg, exc_info=True)
                break
            
            # Emit progress update after successful clip
            self.progress.emit(i + 1)

        # 3. Final Phase: Emit finished signal
        logger.info("Worker finished processing clips.")
        self.finished.emit(created_files)