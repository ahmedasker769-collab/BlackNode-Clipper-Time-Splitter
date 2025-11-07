# modules/ui_manager.py

import sys
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLabel, QListWidget, QMessageBox, QComboBox,
                               QListWidgetItem, QDialog, QApplication, QGridLayout, 
                               QSpinBox, QRadioButton, QFileDialog, QLineEdit, QFrame)
from PySide6.QtCore import QTimer, Qt, Signal, QThread
from PySide6.QtGui import QColor, QCursor
import logging
from pathlib import Path
from collections import deque 

# Local component imports
from .player_widget import PlayerWidget
from .custom_slider import MarkerSlider 
from .video_processor import get_video_duration, generate_clip_timestamps

logger = logging.getLogger("BlackNode-Clipper.UIManager")

# ***************************************************************
# Helper Widgets (AutoSplitDialog and ClipItemWidget)
# ***************************************************************

class AutoSplitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Split Options")
        layout = QGridLayout(self)
        self.duration_radio = QRadioButton("Split by Duration (seconds)")
        self.duration_radio.setChecked(True)
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 600)
        self.duration_spinbox.setValue(10)
        self.number_radio = QRadioButton("Split by Number of Clips")
        self.number_spinbox = QSpinBox()
        self.number_spinbox.setRange(1, 1000)
        self.number_spinbox.setValue(5)
        
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        layout.addWidget(self.duration_radio, 0, 0)
        layout.addWidget(self.duration_spinbox, 0, 1)
        layout.addWidget(self.number_radio, 1, 0)
        layout.addWidget(self.number_spinbox, 1, 1)
        layout.addWidget(ok_button, 2, 0)
        layout.addWidget(cancel_button, 2, 1)
        
    def get_split_parameters(self):
        if self.duration_radio.isChecked(): return {'mode': 'duration', 'value': self.duration_spinbox.value()}
        if self.number_radio.isChecked(): return {'mode': 'number', 'value': self.number_spinbox.value()}
        return None

class ClipItemWidget(QWidget):
    delete_requested = Signal(int)
    def __init__(self, text, row_index, parent=None):
        super().__init__(parent)
        self.row_index = row_index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        self.label = QLabel(text)
        
        # Clip delete button (styled by CSS to be red '❌')
        delete_button = QPushButton("❌") 
        delete_button.setFixedSize(30, 30)
        delete_button.setObjectName("DeleteButton") 
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.row_index))
        
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(delete_button)

# ***************************************************************
# Main UI Class: VideoClipperPanel
# ***************************************************************

class VideoClipperPanel(QWidget):
    # UPDATED SIGNAL: Now sends list of clips and the selected format data (dict)
    clips_confirmed = Signal(list, dict) 
    back_requested = Signal()
    
    SEGMENT_COLORS = [QColor(255,105,180,150), QColor(100,149,237,150), QColor(60,179,113,150), QColor(255,165,0,150), QColor(147,112,219,150)]

    # UPDATED __init__: Accepts supported_formats and default_format_name
    def __init__(self, ffmpeg_path, ffprobe_path, default_output_folder, supported_formats, default_format_name, parent=None):
        super().__init__(parent)
        
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.default_output_folder = default_output_folder
        self.supported_formats = supported_formats
        self.default_format_name = default_format_name
        
        self.video_path = None
        self.clips = []
        self.current_clip = {'start': -1, 'end': -1}
        self.true_duration_ms = -1
        
        # Undo/Redo History Setup
        self.history = deque(maxlen=20) 
        self.history_index = -1
        
        self.main_layout = QVBoxLayout(self) 
        self._setup_ui()
        
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self._connect_signals()
        
        self._save_state()

    def _setup_ui(self):
        self.main_layout.setSpacing(5) 
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel("🎬 BlackNode Video Clipper")
        title.setObjectName("TitleLabel")
        self.main_layout.addWidget(title)
        
        self._setup_output_path_bar()
        
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        
        video_section_widget = QWidget()
        video_section_layout = QVBoxLayout(video_section_widget) 
        video_section_layout.setContentsMargins(0, 0, 0, 0)
        video_section_layout.setSpacing(5)
        
        player_container = QFrame()
        player_container.setObjectName("PlayerContainer")
        player_container_layout = QVBoxLayout(player_container)
        player_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.player_widget = PlayerWidget(self)
        player_container_layout.addWidget(self.player_widget)
        
        self.video_slider = MarkerSlider(Qt.Orientation.Horizontal) 
        self.video_slider.setRange(0, 1000) 
        self.video_slider.setObjectName("VideoSlider")
        
        video_section_layout.addWidget(player_container, 5) 
        video_section_layout.addWidget(self.video_slider, 1) 
        
        # ----------------------------------------------------
        # Controls Layout (with Undo/Redo)
        # ----------------------------------------------------
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 5, 0, 0)
        
        self.undo_button = QPushButton("↩") 
        self.redo_button = QPushButton("↪")
        self.undo_button.setObjectName("UndoRedoButton")
        self.redo_button.setObjectName("RedoButton")
        self.undo_button.setToolTip("Undo Last Clip Action (Ctrl+Z)")
        self.redo_button.setToolTip("Redo Last Clip Action (Ctrl+Y)")
        
        self.rewind_button = QPushButton("⏪︎") 
        self.play_pause_button = QPushButton("▶") 
        self.stop_button = QPushButton("⏹️") 
        self.forward_button = QPushButton("⏩︎")
        
        self.speed_combo = QComboBox() 
        self.speed_combo.addItems(["0.5x", "0.75x", "1x", "1.5x", "2x"]) 
        self.speed_combo.setCurrentText("1x")
        
        controls_layout.addWidget(self.undo_button)
        controls_layout.addWidget(self.redo_button)
        controls_layout.addSpacing(15)
        controls_layout.addWidget(self.rewind_button) 
        controls_layout.addWidget(self.play_pause_button) 
        controls_layout.addWidget(self.stop_button) 
        controls_layout.addWidget(self.forward_button) 
        controls_layout.addSpacing(15) 
        controls_layout.addWidget(QLabel("Speed:")) 
        controls_layout.addWidget(self.speed_combo) 
        controls_layout.addStretch()
        
        self.time_label = QLabel("00:00.00 / 00:00.00") 
        controls_layout.addWidget(self.time_label)
        
        video_section_layout.addLayout(controls_layout, 1) 
        
        # Second Control Bar (Marking and Format Selection)
        sub_controls_layout = QHBoxLayout() 
        sub_controls_layout.setContentsMargins(0, 5, 0, 0)
        
        # --- Format Selection Group ---
        format_group_layout = QHBoxLayout()
        format_group_layout.addWidget(QLabel("Output Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems([f['name'] for f in self.supported_formats])
        self.format_combo.setCurrentText(self.default_format_name)
        format_group_layout.addWidget(self.format_combo)
        sub_controls_layout.addLayout(format_group_layout)
        sub_controls_layout.addStretch() 
        
        self.start_clip_button = QPushButton("🔽 Mark Start") 
        self.end_clip_button = QPushButton("🔼 Mark End & Add") 
        self.auto_split_button = QPushButton("✨ Auto-Split...") 
        self.end_clip_button.setObjectName("AddButton") 
        
        sub_controls_layout.addWidget(self.auto_split_button) 
        sub_controls_layout.addWidget(self.start_clip_button) 
        sub_controls_layout.addWidget(self.end_clip_button) 
        
        video_section_layout.addLayout(sub_controls_layout, 1)
        
        content_layout.addWidget(video_section_widget, 3) 
        
        clip_list_section_layout = QVBoxLayout() 
        clip_list_section_layout.addWidget(QLabel("Clipped Segments:")) 
        self.clip_list_widget = QListWidget() 
        clip_list_section_layout.addWidget(self.clip_list_widget) 
        content_layout.addLayout(clip_list_section_layout, 1) 
        
        self.main_layout.addLayout(content_layout, 1) 
        
        bottom_bar = QHBoxLayout() 
        self.back_button = QPushButton("⬅️ Back") 
        self.confirm_clips_button = QPushButton("✔️ Confirm Clips & Process") 
        self.confirm_clips_button.setObjectName("ConfirmButton") 
        bottom_bar.addWidget(self.back_button) 
        bottom_bar.addStretch() 
        bottom_bar.addWidget(self.confirm_clips_button) 
        self.main_layout.addLayout(bottom_bar)
        
        self.reset_clip_buttons()
        self.back_button.clicked.connect(self.on_back_pressed)
        
        self._update_undo_redo_buttons()

    def _setup_output_path_bar(self):
        """Sets up the input field and button for the output directory."""
        output_widget = QWidget()
        output_layout = QHBoxLayout(output_widget)
        output_layout.setContentsMargins(10, 10, 10, 10)
        
        output_layout.addWidget(QLabel("Output Directory:"))
        
        self.output_path_line = QLineEdit()
        self.output_path_line.setText(str(Path.cwd() / self.default_output_folder))
        output_layout.addWidget(self.output_path_line)
        
        browse_button = QPushButton("Change...")
        browse_button.setObjectName("browseOutputButton")
        browse_button.clicked.connect(self._open_output_dialog)
        output_layout.addWidget(browse_button)
        
        self.main_layout.addWidget(output_widget)
        
    def _open_output_dialog(self):
        """Opens a dialog to select the output directory."""
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Output Directory", 
            self.output_path_line.text()
        )
        if directory:
            self.output_path_line.setText(directory)

    def _connect_signals(self):
        self.video_slider.sliderMoved.connect(self.set_player_position)
        self.play_pause_button.clicked.connect(self.player_widget.toggle_play_pause)
        self.stop_button.clicked.connect(self.stop_video)
        self.rewind_button.clicked.connect(lambda: self.player_widget.seek_video(-10000))
        self.forward_button.clicked.connect(lambda: self.player_widget.seek_video(10000))
        self.speed_combo.currentTextChanged.connect(self.set_playback_rate)
        
        self.start_clip_button.clicked.connect(lambda: self.mark_bound('start')) 
        self.end_clip_button.clicked.connect(lambda: self.mark_bound('end'))
        
        self.auto_split_button.clicked.connect(self.open_auto_split_dialog)
        self.confirm_clips_button.clicked.connect(self.confirm_clips)
        self.timer.timeout.connect(self.update_ui)
        self.video_slider.marker_clicked.connect(self.jump_to_clip_index)
        self.clip_list_widget.currentRowChanged.connect(self.jump_to_selected_clip)
        
        self.video_slider.marker_requested.connect(self._add_clip_point_from_slider)
        
        self.undo_button.clicked.connect(self.undo_action)
        self.redo_button.clicked.connect(self.redo_action)
        
    def set_playback_rate(self, rate_text):
        if self.player_widget:
            try:
                rate = float(rate_text.replace('x', ''))
                self.player_widget.set_rate(rate)
            except ValueError:
                logger.warning(f"Could not parse rate: {rate_text}")
    
    def on_back_pressed(self): 
        self.player_widget.release_player()
        self.back_requested.emit()
    
    def load_video(self, video_path): 
        self.video_path = video_path
        self.clips.clear()
        self.clip_list_widget.clear()
        self.reset_clip_buttons()
        self.video_slider.set_markers([])
        
        self.history.clear() 
        self.history_index = -1
        self._save_state() 
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.true_duration_ms = int(get_video_duration(video_path, self.ffprobe_path) * 1000)
        QApplication.restoreOverrideCursor()
        
        self.player_widget.load_video(video_path)
        QTimer.singleShot(100, self.player_widget.pause)
        self.timer.start()
        
    def open_auto_split_dialog(self):
        if not self.video_path: return
        dialog = AutoSplitDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            params = dialog.get_split_parameters()
            if not params: return

            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            generated_clips_data = None
            try:
                generated_clips_data, _ = generate_clip_timestamps(self.video_path, params, self.ffprobe_path)
            except Exception as e:
                logger.error(f"Error during auto-split calculation: {e}", exc_info=True)
                QMessageBox.critical(self, "Auto-Split Error", 
                                     f"Failed to calculate clips. Check if FFprobe path is correct. Details: {e}")
            finally: 
                QApplication.restoreOverrideCursor()
            
            if generated_clips_data: 
                self.clips.clear()
                self.clip_list_widget.clear() 
                [self.add_clip_to_list(c['start'], c['end'], save_history=False) for c in generated_clips_data]
                self._save_state()
            
    def confirm_clips(self):
        if not self.clips:
            QMessageBox.warning(self, "No Clips", "No clips have been added.")
            return
            
        self.stop_video()
        
        selected_format_name = self.format_combo.currentText()
        selected_format_data = next((f for f in self.supported_formats if f['name'] == selected_format_name), None)
        
        if not selected_format_data:
            QMessageBox.critical(self, "Configuration Error", "Selected output format is invalid.")
            return

        self.clips_confirmed.emit(self.clips, selected_format_data)
        
    def add_clip_to_list(self, start_ms, end_ms, save_history=True): 
        clip = {'start': int(start_ms), 'end': int(end_ms)}
        self.clips.append(clip)
        row_index = len(self.clips) - 1
        item_text = f"Clip {row_index + 1}: [{self._ms_to_time(clip['start'])} -> {self._ms_to_time(clip['end'])}]"
        list_item = QListWidgetItem(self.clip_list_widget)
        item_widget = ClipItemWidget(item_text, row_index)
        item_widget.delete_requested.connect(self.remove_clip)
        list_item.setSizeHint(item_widget.sizeHint())
        self.clip_list_widget.addItem(list_item)
        self.clip_list_widget.setItemWidget(list_item, item_widget)
        self.update_markers()
        
        if save_history:
            self._save_state()
        
    def remove_clip(self, index_to_remove):
        if 0 <= index_to_remove < len(self.clips): 
            self.clips.pop(index_to_remove)
        self.clip_list_widget.takeItem(index_to_remove)
        
        for i in range(self.clip_list_widget.count()):
            item = self.clip_list_widget.item(i)
            widget = self.clip_list_widget.itemWidget(item)
            if widget: 
                widget.row_index = i
                start, end = self.clips[i]['start'], self.clips[i]['end']
                widget.label.setText(f"Clip {i + 1}: [{self._ms_to_time(start)} -> {self._ms_to_time(end)}]")
                
        self.update_markers()
        self._save_state() 

    def _add_clip_point_from_slider(self, normalized_position):
        if self.true_duration_ms <= 0 or not self.player_widget.get_media():
            return
            
        current_time_ms = int(normalized_position * self.true_duration_ms)
        self.player_widget.set_time(current_time_ms)
        
        if self.current_clip['start'] == -1:
            self.mark_bound_at_time(current_time_ms, 'start')
        else:
            self.mark_bound_at_time(current_time_ms, 'end')
            
    def mark_bound_at_time(self, current_time_ms, bound):
        if bound == 'start': 
            self.current_clip['start'] = current_time_ms
            self.start_clip_button.setText(f"Start: {self._ms_to_time(current_time_ms)}")
        elif bound == 'end':
            start_ms = self.current_clip.get('start', -1)
            
            if start_ms >= 0 and current_time_ms > start_ms: 
                self.add_clip_to_list(start_ms, current_time_ms)
                self.reset_clip_buttons()
            else:
                QMessageBox.warning(self, "Invalid Clip", "End time must be after the start time.")
                self.reset_clip_buttons() 
                
        self.update_markers()
        
    def mark_bound(self, bound):
        if not self.player_widget.get_media(): return
        current_time_ms = self.player_widget.get_time()
        self.mark_bound_at_time(current_time_ms, bound)
        
    def reset_clip_buttons(self): 
        self.current_clip = {'start': -1, 'end': -1}
        self.start_clip_button.setText("🔽 Mark Start")
        self.update_markers()
        
    def update_markers(self):
        length = self.true_duration_ms
        markers = []
        if length <= 0: return self.video_slider.set_markers([])
        
        for i, clip in enumerate(self.clips): 
            markers.append((clip['start'] / length, clip['end'] / length, self.SEGMENT_COLORS[i % len(self.SEGMENT_COLORS)]))
        
        if self.current_clip['start'] != -1: 
            start_norm = self.current_clip['start'] / length
            current_pos_norm = self.player_widget.get_position() if self.player_widget.get_media() else start_norm
            end_pos_norm = max(start_norm, current_pos_norm)
            
            markers.append((start_norm, end_pos_norm, self.SEGMENT_COLORS[len(self.clips) % len(self.SEGMENT_COLORS)]))
            
        self.video_slider.set_markers(markers)
        
    def stop_video(self): 
        self.player_widget.stop_video()
        self.timer.stop()
        self.reset_clip_buttons()
    
    def update_ui(self):
        if not self.player_widget.get_media(): return
        current_time_ms = self.player_widget.get_time()
        total_time_ms = self.true_duration_ms
        
        if total_time_ms > 0 and not self.video_slider.isSliderDown(): 
            self.video_slider.setValue(int((current_time_ms / total_time_ms) * 1000))
            
        self.time_label.setText(f"{self._ms_to_time(current_time_ms)} / {self._ms_to_time(total_time_ms)}")
        self.play_pause_button.setText("⏸️" if self.player_widget.is_playing() else "▶")
        self.update_markers()
        
    def set_player_position(self, value): 
        self.player_widget.set_position(value / 1000.0)
    
    def jump_to_selected_clip(self, row):
        if 0 <= row < len(self.clips): 
            self.player_widget.set_time(self.clips[row]['start'])
        
    def jump_to_clip_index(self, index):
        if 0 <= index < self.clip_list_widget.count(): 
            self.clip_list_widget.setCurrentRow(index)
        
    def _ms_to_time(self, ms):
        if ms < 0: ms = 0
        s, ms_rem = divmod(int(ms), 1000)
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}.{int(ms_rem/10):02d}"

    # ***************************************************************
    # Undo/Redo History Management Functions 
    # ***************************************************************
    
    def _save_state(self):
        """Saves the current clips state to the history."""
        while len(self.history) > self.history_index + 1:
            self.history.pop()
            
        current_state = [clip.copy() for clip in self.clips]
        self.history.append(current_state)
        
        self.history_index = len(self.history) - 1
        self._update_undo_redo_buttons()

    def _load_state(self, index):
        """Loads a specific state from history."""
        if 0 <= index < len(self.history):
            state = self.history[index]
            self.clips.clear()
            self.clips.extend([clip.copy() for clip in state])
            
            self._sync_clips_list_widget()
            self.update_markers()
            self.history_index = index
            self._update_undo_redo_buttons()
            
    def _sync_clips_list_widget(self):
        """Rebuilds the QListWidget to reflect the current self.clips list."""
        self.clip_list_widget.clear()
        for i, clip in enumerate(self.clips):
            row_index = i
            item_text = f"Clip {row_index + 1}: [{self._ms_to_time(clip['start'])} -> {self._ms_to_time(clip['end'])}]"
            list_item = QListWidgetItem(self.clip_list_widget)
            item_widget = ClipItemWidget(item_text, row_index)
            item_widget.delete_requested.connect(self.remove_clip)
            list_item.setSizeHint(item_widget.sizeHint())
            self.clip_list_widget.addItem(list_item)
            self.clip_list_widget.setItemWidget(list_item, item_widget)
            
    def undo_action(self):
        """Moves back one step in history."""
        if self.history_index > 0:
            self._load_state(self.history_index - 1)
            
    def redo_action(self):
        """Moves forward one step in history."""
        if self.history_index < len(self.history) - 1:
            self._load_state(self.history_index + 1)
            
    def _update_undo_redo_buttons(self):
        """Updates the enabled state of the undo/redo buttons."""
        self.undo_button.setEnabled(self.history_index > 0)
        self.redo_button.setEnabled(self.history_index < len(self.history) - 1)