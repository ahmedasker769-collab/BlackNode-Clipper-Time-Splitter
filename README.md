BlackNode-Clipper: Precision Video Splitting Tool
BlackNode-Clipper is a standalone, efficient application built with PySide6 and VLC for precisely splitting large video files into smaller, timestamped clips. It leverages FFmpeg for video processing, running the demanding tasks in the background to ensure a smooth, non-freezing Graphical User Interface (GUI).

🌟 Key Features
VLC Playback Control: Integrated VLC player for smooth video viewing, seeking, and playback speed control.

Time-Based Clipping: Manually mark clip start and end points with high accuracy.

Automated Splitting: Option to automatically generate clips based on a fixed duration or a desired number of clips.

Visual Marker Slider: A custom MarkerSlider component visually displays all selected clips on the video timeline.

Non-Blocking Processing: Uses QThread and QProcess to run FFmpeg commands in the background, keeping the UI responsive.

🛠️ Prerequisites
Before you start, ensure you have the following installed and configured:

Python 3.x

VLC Media Player: The python-vlc library requires a local installation of the VLC media player.

FFmpeg & FFprobe: The core processing relies on FFmpeg tools. You must download ffmpeg.exe and ffprobe.exe and place them in the root directory of the project (next to main.py).

📦 Setup and Installation
It is highly recommended to use a Virtual Environment (venv) to keep your dependencies isolated.

1. Virtual Environment Setup
Bash

# 1. Create the virtual environment
python -m venv venv

# 2. Activate the environment (on Windows)
.\venv\Scripts\activate
2. Install Dependencies
With the environment activated, install the required libraries and Nuitka:

Bash

pip install -r requirements.txt
pip install nuitka
⚙️ Configuration (config.yaml)
The application is configured to look for ffmpeg.exe and ffprobe.exe in its execution directory. No path changes are necessary if you placed the executables correctly.

YAML

# config.yaml
ffmpeg_paths:
  # The application will look for these in the same directory as the final executable.
  ffmpeg: ffmpeg
  ffprobe: ffprobe
🔨 Building the Executable (Nuitka)
To compile the application into a single executable file, use the provided build_nuitka.bat script:

Ensure your virtual environment is active.

Ensure ffmpeg.exe and ffprobe.exe are in the project root.

Run the batch file:

Bash

build_nuitka.bat
Critical Post-Build Steps (VLC and FFmpeg)
The build_nuitka.bat script automatically handles including project files and copies FFmpeg/FFprobe to the dist folder. However, due to how VLC loads its components, you may need one manual step:

VLC Plugins: If video playback fails in the final executable, you must copy the entire plugins folder from your original VLC installation (where libvlc.dll is located) and place it directly into the Nuitka dist output folder.

🚀 How to Use the Clipper
Launch the application (via main.py or the compiled .exe).

Click Select Video to choose your source file.

Manual Clipping:

Navigate the video using the slider or player controls.

Click 🔽 Mark Start at the desired beginning.

Click 🔼 Mark End & Add at the desired end to add the clip to the list.

Auto-Split: Click ✨ Auto-Split... and select your preferred method (by Duration or by Number of Clips).

Once your clips list is finalized, click ✔️ Confirm Clips & Process.

The FFmpeg process will run in the background. The final clips will be saved in the newly created clipped_output folder.