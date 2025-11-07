# main.py

import sys
import os
import yaml
import logging
from PySide6.QtWidgets import (QApplication, QMainWindow, QMessageBox, QProgressDialog,
                               QStackedWidget) 
from PySide6.QtCore import QThread, Signal, Qt
from pathlib import Path

# Import custom components 
from modules.ui_manager import VideoClipperPanel
from modules.workers import VideoSplitterWorker
from modules.video_processor import ensure_folder
from modules.file_selector_panel import VideoSelectorPanel 

# Setup the Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlackNode-Clipper.Main")

# ***************************************************************
# PROJECT SETTINGS AND CONFIGURATION
# ***************************************************************

CONFIG_FILE = "config.yaml"
STYLE_FILE = "style.css" 

def load_config(file_path):
    """
    Loads configuration from config.yaml, ensuring UTF-8 encoding. 
    If file does not exist, creates a default one.
    """
    default_config = {
        'ffmpeg_paths': {'ffmpeg': 'ffmpeg', 'ffprobe': 'ffprobe'},
        'system_settings': {'default_output_folder_name': 'clipped_output'},
        'output_settings': {
            'default_segment_duration_seconds': 10,
            'resolution': '1080p',
            'video_bitrate': '5000k',
            'default_output_format': 'MP4 (H.264)', 
        },
        'supported_formats': [
            {'name': 'MP4 (H.264)', 'extension': 'mp4', 'video_codec': 'libx264', 'audio_codec': 'aac', 'options': ['-crf', '23', '-pix_fmt', 'yuv420p']},
            {'name': 'WebM (VP9)', 'extension': 'webm', 'video_codec': 'libvpx-vp9', 'audio_codec': 'libopus', 'options': ['-crf', '30', '-b:v', '0']},
            {'name': 'GIF (No Audio)', 'extension': 'gif', 'video_codec': 'gif', 'audio_codec': 'an', 'options': ['-r', '15']},
            {'name': 'Stream Copy (Original Format)', 'extension': 'mp4', 'video_codec': 'copy', 'audio_codec': 'copy', 'options': []}
        ]
    }

    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            for key, default_value in default_config.items():
                if key not in config:
                    config[key] = default_value
                elif isinstance(default_value, dict) and isinstance(config[key], dict):
                    config[key] = {**default_value, **config[key]}

            if not config.get('supported_formats'):
                config['supported_formats'] = default_config['supported_formats']

            return config
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True, sort_keys=False)
            logger.warning(f"Configuration file {file_path} not found. Default configuration created.")
            return default_config
            
    except Exception as e:
        logger.error(f"Error loading/creating config file: {e}. Using internal defaults.", exc_info=True)
        return default_config


# ***************************************************************
# MAIN WINDOW CLASS
# ***************************************************************

class MainWindow(QMainWindow):
    def __init__(self, config_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BlackNode Video Clipper")
        self.setMinimumSize(800, 600)
        
        self.config_data = config_data 
        
        self.video_path = None
        
        # UI components: Use QStackedWidget to manage panels
        self.main_stack = QStackedWidget(self)
        self.setCentralWidget(self.main_stack)
        
        # 1. Setup Selector Panel (Index 0: Default Start Screen)
        self.selector_panel = VideoSelectorPanel()
        self.selector_panel.video_selected.connect(self.load_clipper_panel) 
        self.main_stack.addWidget(self.selector_panel)
        
        # 2. Clipper Panel (Created later when a file is selected)
        self.clipper_panel = None
        
        # Processing setup
        self.worker = None
        self.thread = None
        self.progress_dialog = None
        
        self.main_stack.setCurrentWidget(self.selector_panel)

    def load_clipper_panel(self, video_path):
        """Initializes the clipper panel with the selected video and switches the view."""
        
        if self.clipper_panel is None:
            
            ffmpeg_path = self.config_data['ffmpeg_paths']['ffmpeg']
            ffprobe_path = self.config_data['ffmpeg_paths']['ffprobe']
            default_folder = self.config_data['system_settings']['default_output_folder_name']
            
            supported_formats = self.config_data.get('supported_formats', [])
            default_format_name = self.config_data['output_settings']['default_output_format']
            
            self.clipper_panel = VideoClipperPanel(
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                default_output_folder=default_folder,
                supported_formats=supported_formats, 
                default_format_name=default_format_name
            )
            
            self.clipper_panel.clips_confirmed.connect(self.start_processing)
            self.clipper_panel.back_requested.connect(self.unload_clipper_panel) 
            
            self.main_stack.addWidget(self.clipper_panel)
            
        self.video_path = video_path
        self.clipper_panel.load_video(video_path)
        self.main_stack.setCurrentWidget(self.clipper_panel)

    def unload_clipper_panel(self):
        """Stops the player and switches back to the selector screen."""
        if self.clipper_panel:
            self.clipper_panel.stop_video()
        self.main_stack.setCurrentWidget(self.selector_panel)
        self.video_path = None

    # تم تعديل ترتيب إشارات الربط هنا لمنع تجميد الواجهة بعد انتهاء المعالجة
    def start_processing(self, clips, format_data): 
        logger.info(f"Starting processing for {len(clips)} clips with format: {format_data['name']}")
        
        # 1. Get paths and configuration
        video_path = self.video_path 
        output_folder = self.clipper_panel.output_path_line.text()
        ffmpeg_path = self.config_data['ffmpeg_paths']['ffmpeg']
        ffprobe_path = self.config_data['ffmpeg_paths']['ffprobe']
        
        # 2. Ensure the output folder exists
        try:
            ensure_folder(output_folder)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create output directory: {e}")
            logger.error(f"Failed to create output directory: {e}", exc_info=True)
            return
            
        # 3. Setup Worker Thread
        self.thread = QThread()
        self.worker = VideoSplitterWorker(
            video_path=video_path,
            output_folder=output_folder,
            clips=clips,
            ffprobe_path=ffprobe_path, 
            ffmpeg_path=ffmpeg_path,
            format_data=format_data, 
            app_config=self.config_data 
        )
        
        self.worker.moveToThread(self.thread)
        
        # 4. Connect signals (FIXED ORDER FOR STABILITY)
        self.thread.started.connect(self.worker.run)
        
        # A. UI Feedback/Operation slots (Must run first: progress updates, error messages, final success message)
        self.worker.progress.connect(self._update_progress_dialog)
        self.worker.error.connect(self._handle_worker_error)
        self.worker.finished.connect(self._processing_finished) 
        
        # B. Cleanup slots (Must run after the final UI operation (_processing_finished) returns)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        # 5. Show progress dialog and start
        self.progress_dialog = QProgressDialog(
            "Splitting video clips...", 
            "Cancel", 
            0, 
            len(clips), 
            self
        )
        self.progress_dialog.setWindowTitle("Processing")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.canceled.connect(self.worker.stop)
        self.progress_dialog.show()
        
        self.thread.start()
        
    def _update_progress_dialog(self, progress):
        """Updates the progress dialog with the number of finished clips."""
        if self.progress_dialog:
            self.progress_dialog.setValue(progress)
            self.progress_dialog.setLabelText(f"Processing clip {progress} of {self.progress_dialog.maximum()}...")

    def _handle_worker_error(self, message):
        """Handles errors reported by the worker thread."""
        if self.progress_dialog:
            self.progress_dialog.close()
        
        if self.thread and self.thread.isRunning():
            self.thread.quit()
        
        QMessageBox.critical(self, "Processing Error", message)
        logger.error(message)

    def _processing_finished(self, created_files):
        """Handles completion of the worker thread."""
        if self.progress_dialog:
            self.progress_dialog.close()
        
        if created_files:
            file_list = "\n".join([str(Path(f).name) for f in created_files])
            QMessageBox.information(
                self, 
                "Success", 
                f"Successfully processed {len(created_files)} clips!\nSaved in: {self.clipper_panel.output_path_line.text()}\nFiles:\n{file_list}"
            )
        else:
            QMessageBox.warning(
                self, 
                "Finished", 
                "Processing finished, but no files were created (possibly cancelled or all failed)."
            )

# ***************************************************************
# APPLICATION ENTRY POINT
# ***************************************************************

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        
        if os.path.exists(STYLE_FILE):
            try:
                with open(STYLE_FILE, "r") as f:
                    app.setStyleSheet(f.read())
                logger.info(f"Loaded external style sheet: {STYLE_FILE}")
            except Exception as e:
                logger.error(f"Failed to load style sheet: {e}")
        
        config_data = load_config(CONFIG_FILE)
        logger.info("Configuration loaded successfully.")
        
        main_win = MainWindow(config_data)
        main_win.show()
        
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical(f"A critical error occurred during application startup: {e}", exc_info=True)
        sys.exit(1)