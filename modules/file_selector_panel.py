# modules/file_selector_panel.py

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog)
from PySide6.QtCore import Signal, Qt
import logging

logger = logging.getLogger("BlackNode-Clipper.FileSelector")

class VideoSelectorPanel(QWidget):
    """
    Initial panel for selecting the video file.
    """
    # Signal that emits the full path of the selected video file (str)
    video_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        # Main layout, centered
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Title Label
        title = QLabel("🎬 BlackNode Video Clipper")
        title.setObjectName("TitleLabel")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Instruction Label
        instruction = QLabel("Please select a video file to begin clipping.")
        instruction.setObjectName("InstructionLabel")
        layout.addWidget(instruction, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Select Button
        self.select_button = QPushButton("📂 Select Video File")
        self.select_button.setObjectName("SelectFileButton")
        self.select_button.clicked.connect(self.open_file_dialog)
        layout.addWidget(self.select_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def open_file_dialog(self):
        """
        Opens the file selection dialog with a broad filter for common video formats.
        This ensures maximum input compatibility.
        """
        # A broad filter covering the most common video container formats
        video_filter = "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts *.3gp *.ogv);;All Files (*)"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video File",
            "",
            video_filter
        )
        
        if file_path:
            logger.info(f"Video file selected: {file_path}")
            self.video_selected.emit(file_path)
        else:
            logger.info("File selection cancelled.")