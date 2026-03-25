# tuitify

A Python-based terminal music player that provides a functional interface for searching and playing music directly within your command line.

## Working

The application uses a Terminal User Interface (TUI) to bridge the gap between command-line efficiency and a visual music player experience. It utilizes custom styling for the interface and specialized audio libraries to handle playback directly through system hardware.

## Features

* **Integrated Search:** Find tracks directly through the terminal interface.
* **Audio Playback:** Full playback control within the console environment.
* **TUI Interface:** A structured layout that organizes search results and player controls using terminal CSS.
* **Native Audio Support:** Uses specific system drivers to ensure low-latency audio performance.

## Setup

To get the application running on your local machine, follow these steps:

### 1. Clone the Repository

```bash
git clone https://github.com/Arihasaheadache/tuitify.git
cd tuitify

```

### 2. Install Dependencies

Ensure you have Python 3.x installed, then run the following to install the necessary libraries:

```bash
pip install -r requirements.txt

```

### 3. Audio Configuration

The application requires the included DLL files to communicate with your audio hardware. Ensure the `dll` folder remains in the root directory of the project.

### 4. Running the Program

Launch the player by executing the main script:

```bash
python main.py

```
