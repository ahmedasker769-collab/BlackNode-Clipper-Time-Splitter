# main.py

import sys
import os
import yaml
import logging
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QFileDialog, QMessageBox, QPushButton, QLineEdit,
                               QHBoxLayout, QLabel, QProgressDialog, QGridLayout)
from PySide6.QtCore import QThread, Signal, Qt
from pathlib import Path

# Import custom components (Fixed imports)
from modules.ui_manager import VideoClipperPanel
from modules.workers import VideoSplitterWorker
from modules.video_processor import ensure_folder

# Setup the Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlackNode-Clipper.Main")

# ***************************************************************
# PROJECT SETTINGS AND CONFIGURATION
# ***************************************************************

CONFIG_FILE = "config.yaml"
OUTPUT_FOLDER = "clipped_output" 
STYLE_FILE = "style.css" # File to load the custom theme

def load_config(file_path):
    """
    Loads configuration from config.yaml, ensuring UTF-8 encoding. 
    If file does not exist, creates a default one.
    """
    # Default minimum configuration for safety
    default_config = {
        'ffmpeg_paths': {'ffmpeg': 'ffmpeg', 'ffprobe': 'ffprobe'},
        'system_settings': {'default_output_folder_name': 'clipped_output'}
    }
    
    if not os.path.exists(file_path):
        # Create default config if missing (with UTF-8)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, sort_keys=False)
            logger.warning(f"Created default '{file_path}'. Please verify FFmpeg/FFprobe paths.")
        except Exception as e:
            logger.error(f"Error creating default config file: {e}")
        return default_config
        
    try:
        # Load config with explicit UTF-8 encoding to prevent 'charmap' errors
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_config = yaml.safe_load(f)
            
            # Merge with defaults to ensure all keys are present
            if loaded_config:
                final_config = default_config.copy()
                final_config.update(loaded_config)
                return final_config
            return default_config
            
    except Exception as e:
        logger.critical(f"Error loading config file '{file_path}'. Using defaults. Error: {e}")
        return default_config

# ***************************************************************
# MAIN WINDOW CLASS (Correctly placed before the execution block)
# ***************************************************************

class MainWindow(QMainWindow):
    """
    Main application window managing video selection, configuration,
    and launching the clipping/processing panel.
    """
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("BlackNode Video Clipper")
        self.setGeometry(100, 100, 1200, 800)
        
        self.config = config
        
        # Handle paths and output folder dynamically from config
        self.ffmpeg_path = config['ffmpeg_paths']['ffmpeg']
        self.ffprobe_path = config['ffmpeg_paths']['ffprobe']
        self.output_folder_name = config.get('system_settings', {}).get('default_output_folder_name', OUTPUT_FOLDER)
        
        self.source_video_path = None
        self.splitter_thread = None
        self.splitter_worker = None
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        # 1. Setup the Video Input Bar
        self._setup_input_bar()
        
        # 2. Setup the Clipping Panel
        self.clipper_panel = VideoClipperPanel(
            ffmpeg_path=self.ffmpeg_path, 
            ffprobe_path=self.ffprobe_path,
            default_output_folder=self.output_folder_name
        )
        self.layout.addWidget(self.clipper_panel)
        self.clipper_panel.setEnabled(False)
        
        self._connect_signals()
        
        logger.info(f"FFmpeg Path: {self.ffmpeg_path} | FFprobe Path: {self.ffprobe_path}")
        logger.info("Application is running. Ready for video selection.")

    def _setup_input_bar(self):
        """Creates the visually attractive input section, setting objectName for styling."""
        input_widget = QWidget()
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(10, 10, 10, 10)
        
        # Style improvements: using clearer labels and buttons
        input_layout.addWidget(QLabel("🎥 Video Source:"))
        
        self.video_path_line = QLineEdit()
        self.video_path_line.setPlaceholderText("Select source video file (e.g., C:/Videos/source.mp4)...")
        self.video_path_line.textChanged.connect(self._handle_video_path_change)
        input_layout.addWidget(self.video_path_line)
        
        self.select_video_button = QPushButton("Browse...")
        self.select_video_button.setObjectName("browseButton") # Crucial for CSS styling
        self.select_video_button.clicked.connect(self._open_file_dialog)
        input_layout.addWidget(self.select_video_button)
        
        self.layout.addWidget(input_widget)

    def _connect_signals(self):
        self.clipper_panel.clips_confirmed.connect(self.start_splitting)
        self.clipper_panel.back_requested.connect(self._handle_back_request)

    def _handle_video_path_change(self, path):
        """Validates the path and loads the video into the clipper panel."""
        if os.path.exists(path) and Path(path).suffix.lower() in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
            self.source_video_path = path
            self.clipper_panel.load_video(self.source_video_path)
            self.clipper_panel.setEnabled(True)
            logger.info(f"Loaded video: {path}")
        else:
            self.clipper_panel.setEnabled(False)
            # Ensure player is released if path is invalid
            if hasattr(self.clipper_panel, 'player_widget') and self.clipper_panel.player_widget is not None:
                self.clipper_panel.player_widget.release_player()
            if path:
                logger.warning(f"Path is not a valid video file: {path}")

    def _open_file_dialog(self):
        """Opens a file dialog to select the video."""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Video File", 
            "", 
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm)"
        )
        if path:
            self.video_path_line.setText(path)
            
    def _handle_back_request(self):
        """Handles cleanup when the user requests to go back (in future updates)."""
        logger.info("Clipper panel requested back. Cleaning up.")
        if hasattr(self.clipper_panel, 'player_widget') and self.clipper_panel.player_widget is not None:
            self.clipper_panel.player_widget.release_player()
        self.video_path_line.clear() # Clear line to reset state
        
    def start_splitting(self, clips):
        """Initiates the video splitting process in a QThread."""
        if not self.source_video_path or not clips:
            QMessageBox.warning(self, "Error", "Please select a valid video file and add at least one clip.")
            return
        
        try:
            output_dir = self.clipper_panel.output_path_line.text()
            if not Path(output_dir).is_absolute():
                output_dir = str(Path.cwd() / output_dir)
        except AttributeError:
            logger.error("Output path line not found in VideoClipperPanel. Using default path.")
            output_dir = str(Path.cwd() / self.output_folder_name)
            
        ensure_folder(output_dir)
        
        logger.info(f"Starting splitting of {len(clips)} clips into: {output_dir}")
        
        # 1. Setup Worker
        self.splitter_thread = QThread()
        self.splitter_worker = VideoSplitterWorker(
            video_path=self.source_video_path,
            output_folder=output_dir, 
            clips=clips,
            ffprobe_path=self.ffprobe_path,
            ffmpeg_path=self.ffmpeg_path,
            app_config=self.config # Passing config
        )
        
        self.splitter_worker.moveToThread(self.splitter_thread)
        self.splitter_thread.started.connect(self.splitter_worker.run)
        
        # 2. Setup Progress Dialog
        self.progress_dialog = QProgressDialog(
            f"Processing clips with FFmpeg into '{Path(output_dir).name}'...", 
            "Cancel", 
            0, 
            len(clips), 
            self
        )
        self.progress_dialog.setWindowTitle("Video Splitter Progress")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        
        # 3. Connect Signals
        self.splitter_worker.progress.connect(self._update_progress_dialog)
        self.splitter_worker.finished.connect(self._splitting_finished)
        self.splitter_worker.finished.connect(self.splitter_thread.quit)
        self.progress_dialog.canceled.connect(self.splitter_worker.stop)
        self.progress_dialog.canceled.connect(self.splitter_thread.quit)
        self.splitter_thread.finished.connect(self._cleanup_thread)

        # 4. Start Process
        self.progress_dialog.show()
        self.splitter_thread.start()

    def _update_progress_dialog(self, value):
        self.progress_dialog.setValue(value)
        self.progress_dialog.setLabelText(f"Processing clip {value} of {self.progress_dialog.maximum()}...")

    def _splitting_finished(self, created_files):
        self.progress_dialog.close()
        
        if created_files:
            QMessageBox.information(
                self, 
                "Splitting Complete", 
                f"Successfully created {len(created_files)} clips in the '{Path(created_files[0]).parent.name}' folder."
            )
        else:
            QMessageBox.warning(
                self, 
                "Splitting Failed", 
                "No clips were created or the process was cancelled/failed."
            )

    def _cleanup_thread(self):
        """Safely cleans up threads and workers."""
        if self.splitter_thread:
            self.splitter_thread.deleteLater()
            self.splitter_worker.deleteLater()
            self.splitter_thread = None
            self.splitter_worker = None
            
    def closeEvent(self, event):
        """Ensure all resources are released upon closing the main window."""
        self._cleanup_thread()
        if hasattr(self.clipper_panel, 'player_widget') and self.clipper_panel.player_widget is not None:
            self.clipper_panel.player_widget.release_player()
        super().closeEvent(event)


# ***************************************************************
# APPLICATION ENTRY POINT (Fixed location and structure)
# ***************************************************************

if __name__ == '__main__':
    try:
        # Initialize Application
        app = QApplication(sys.argv)
        
        # ----------------------------------------------------
        # Load and Apply External Theme Styling (style.css)
        # ----------------------------------------------------
        if os.path.exists(STYLE_FILE):
            try:
                with open(STYLE_FILE, "r") as f:
                    app.setStyleSheet(f.read())
                logger.info(f"Loaded external style sheet: {STYLE_FILE}")
            except Exception as e:
                logger.error(f"Failed to load style sheet: {e}")
        # ----------------------------------------------------
        
        # 1. Load Configuration (using the fixed function)
        config_data = load_config(CONFIG_FILE)
        logger.info("Configuration loaded successfully.")
        
        # 2. Create the Main Window 
        main_win = MainWindow(config_data)
        
        # Show the window 
        main_win.show()
        
        # 3. Start the main event loop
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical(f"A critical error occurred during application startup: {e}", exc_info=True)
        # Exit with a non-zero code to indicate failure
        sys.exit(1)