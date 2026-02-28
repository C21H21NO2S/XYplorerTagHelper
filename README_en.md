# XYplorerTagHelper 🏷️

English | [简体中文](README.md) | [Manual](manual_en.md)

An advanced tag helper and filtering tool tailored specifically for the powerful file manager **XYplorer**. 
Through a modern visual interface, it helps you manage file tags more efficiently, generate complex search syntaxes, and fully customize your workspaces.

<img width="1100" height="960" alt="XYplorerTagHelper 1 2 2-Dark   Light" src="https://github.com/user-attachments/assets/a756e291-1d21-42f7-97cd-5285437fa03b" />

## ✨ Core Features

* **🚀 Visual Tag Tree**: Say goodbye to tedious plain text input. Supports infinite levels of tag grouping and free drag-and-drop sorting.
* **🔍 Smart Filter Builder**: Generate and send advanced XYplorer search syntaxes automatically by clicking and combining conditions (Path, File Name, Remarks, Labels, Ratings, Size, Date).
* **🎨 Modern Native UI**: Built-in Dark and Light dual themes. Supports custom component colors and provides an immersive native Windows 11 title bar experience.
* **💼 Multi-Workspace Management**: Isolates tag data based on different workflows (e.g., "Default Workspace", "Project Status") and supports fast switching.
* **⚡ Lightning-Fast Interaction**: Intelligently reads and activates tags from the clipboard, and supports one-click synchronization with XYplorer's native Labels.

## 📥 Download and Installation (Recommended for Non-Programmers)

If you just want to use the software directly without configuring any coding environment:
1. Go to the [Releases page](https://github.com/C21H21NO2S/XYplorerTagHelper/releases) of this project.
2. Download the latest version of `XYplorerTagHelper_ver.7z`.
3. After extracting, double-click `XYplorerTagHelper.exe` to start using it.

## 💻 Running from Source Code (For Developers)

If you have a Python environment installed, you can run or further develop it by following these steps (requirements: pywebview≥4.0):

```bash
# Clone the repository
git clone https://github.com/C21H21NO2S/XYplorerTagHelper.git
cd XYplorerTagHelper

# Install dependencies (The core dependency is pywebview)
pip install -r requirements.txt

# Run the program
python XYplorerTagHelper.py
```

## 🛠️ Preparation for Use with XYplorer
To allow the Helper to smoothly control XYplorer, please ensure that in the software settings (click the gear icon ⚙️ in the top right corner):

The XYplorer Path is configured correctly (e.g., C:\XYplorer\XYplorer.exe or just the folder path).

## 🙋‍♂️ About the Author & Feedback
I am a coding beginner but a passionate creator! This tool was born to solve the pain points I encountered myself while using XYplorer.

If you encounter any bugs or have great feature suggestions during use, you are welcome to submit them in the GitHub Issues!

## 📄 Open Source License
[MIT License](https://www.google.com/search?q=LICENSE)
