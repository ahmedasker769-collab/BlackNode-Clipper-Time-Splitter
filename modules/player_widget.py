# modules/player_widget.py

import sys
import vlc
import logging
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QSlider, QLabel)
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt, QTimer, Signal

logger = logging.getLogger("BlackNode-Clipper.PlayerWidget")

class PlayerWidget(QWidget):
    # Signal to report new time for external elements (e.g., UI Manager)
    time_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instance = None
        self.mediaplayer = None
        
        self.is_setting_position = False # Flag to prevent auto-update during user drag
        
        # Video frame setup
        self.videoframe = QFrame()
        palette = self.videoframe.palette()
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(0, 0, 0))
        self.videoframe.setPalette(palette)
        self.videoframe.setAutoFillBackground(True)
        
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.addWidget(self.videoframe)
        
        self._setup_seek_controls() # New control bar setup
        
        self.setLayout(self.vbox)

        # Timer for UI updates
        self.timer = QTimer(self)
        self.timer.setInterval(100) # Update every 100 milliseconds
        self.timer.timeout.connect(self.update_ui)
        
    def _setup_seek_controls(self):
        """Sets up the horizontal seek bar and time labels."""
        control_bar = QWidget()
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(5, 5, 5, 5)
        
        # Time Labels
        self.current_time_label = QLabel("00:00:00")
        self.total_time_label = QLabel(" / 00:00:00")
        
        # Seek Slider (Range 0 to 1000 for VLC position 0.0 to 1.0)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000) 
        
        # Connect slider events for seek functionality
        self.position_slider.sliderReleased.connect(self._set_position_by_slider)
        self.position_slider.sliderPressed.connect(self._start_setting_position)
        
        # Add controls to layout
        control_layout.addWidget(self.current_time_label)
        control_layout.addWidget(self.position_slider)
        control_layout.addWidget(self.total_time_label)
        
        self.vbox.addWidget(control_bar)
        
    def _start_setting_position(self):
        """Called when user presses the slider, stopping auto-update."""
        self.is_setting_position = True
        
    def _set_position_by_slider(self):
        """Called when user releases the slider, setting new position in VLC."""
        if self.mediaplayer:
            # VLC position is a float between 0.0 and 1.0
            new_position = self.position_slider.value() / 1000.0
            self.mediaplayer.set_position(new_position)
            self.is_setting_position = False
            self.update_ui() # Force immediate UI update

    def update_ui(self):
        """Updates the slider position and time display."""
        if not self.mediaplayer:
            return

        # Update slider only if the user is NOT currently moving it
        if not self.is_setting_position:
            # Get position (0.0 to 1.0) and convert to slider range (0-1000)
            position = self.mediaplayer.get_position()
            self.position_slider.setValue(int(position * 1000))
        
        current_time_ms = self.mediaplayer.get_time()
        length_ms = self.mediaplayer.get_length()

        # Emit time in milliseconds for the clipper panel to sync markers
        self.time_changed.emit(current_time_ms) 
        
        # Update time labels
        self.current_time_label.setText(self._ms_to_hms(current_time_ms))
        self.total_time_label.setText(f" / {self._ms_to_hms(length_ms)}")


    def _ms_to_hms(self, ms):
        """Converts milliseconds to HH:MM:SS format."""
        s = int(ms / 1000)
        h = s // 3600
        s %= 3600
        m = s // 60
        s %= 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _initialize_vlc(self):
        if self.instance is None:
            logger.info("Initializing new VLC instance...")
            
            vlc_options = [
                '--avcodec-hw=none',
                '--no-osd',
                '--no-video-title-show',
                '--ignore-config',
                '--disable-screensaver',
                '--quiet',
            ]
            self.instance = vlc.Instance(vlc_options)
            
        if self.instance is None:
            logger.critical("VLC Instance creation failed!")
            return

        if self.mediaplayer is None:
            self.mediaplayer = self.instance.media_player_new()
            if sys.platform.startswith("win"):
                self.mediaplayer.set_hwnd(self.videoframe.winId())

    def load_video(self, path: str):
        self._initialize_vlc()
        if not self.mediaplayer:
            logger.error("Media player is not available. Cannot load video.")
            return
        media = self.instance.media_new(path)
        self.mediaplayer.set_media(media)
        self.play()
        
        # Start the timer when video loads
        if not self.timer.isActive():
            self.timer.start()

    def release_player(self):
        # Stops and completely releases all VLC resources
        logger.info("Releasing all VLC resources...")
        if self.timer.isActive():
            self.timer.stop()
        if self.mediaplayer:
            if self.mediaplayer.is_playing():
                self.mediaplayer.stop()
            self.mediaplayer.release()
            self.mediaplayer = None
            
        if self.instance:
            self.instance.release()
            self.instance = None
            
    # Other control functions
    def play(self):
        if self.mediaplayer: self.mediaplayer.play()
    def pause(self):
        if self.mediaplayer: self.mediaplayer.pause()
    def toggle_play_pause(self):
        if self.mediaplayer and self.mediaplayer.is_playing(): self.pause()
        else: self.play()
    def stop_video(self):
        if self.mediaplayer: self.mediaplayer.stop()
    def seek_video(self, time_change_ms):
        if self.mediaplayer: self.mediaplayer.set_time(max(0, self.mediaplayer.get_time() + time_change_ms))
    def set_position(self, pos: float):
        if self.mediaplayer: self.mediaplayer.set_position(pos)
    def get_position(self) -> float:
        return self.mediaplayer.get_position() if self.mediaplayer else 0.0
    def get_length(self) -> int:
        return self.mediaplayer.get_length() if self.mediaplayer else 0
    def get_time(self) -> int:
        return self.mediaplayer.get_time() if self.mediaplayer else 0
    def set_time(self, ms: int):
        if self.mediaplayer: self.mediaplayer.set_time(ms)
    def set_rate(self, rate: float):
        if self.mediaplayer: self.mediaplayer.set_rate(rate)
    def get_state(self):
        return self.mediaplayer.get_state() if self.mediaplayer else vlc.State.Error
    def get_media(self):
        return self.mediaplayer.get_media() if self.mediaplayer else None
    def is_playing(self) -> bool:
        return self.mediaplayer.is_playing() if self.mediaplayer else False