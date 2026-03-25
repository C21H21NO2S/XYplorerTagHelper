# XYplorerTagHelper User Guide

## Table of Contents

- [🏗️ I. Software Architecture and Underlying Logic](#️-i-software-architecture-and-underlying-logic)
- [⚙️ II. Initial Configuration and Workspace Management (Workspace)](#️-ii-initial-configuration-and-workspace-management-workspace)
  - [1. Basic Settings](#1-basic-settings)
  - [2. Advanced Workspace Operations](#2-advanced-workspace-operations)
- [🎛️ III. Four Core Action Buttons (Top Action Buttons)](#️-iii-four-core-action-buttons-top-action-buttons)
  - [1. 🔍 Search](#1--search)
  - [2. 🏷️ Apply Tag / Remove Tag (Tag)](#2-️-apply-tag--remove-tag-tag)
  - [3. 📖 Read Tags (Read)](#3--read-tags-read)
  - [4. 🗑️ Clear](#4-️-clear)
- [🎛️ IV. Composite Filter Area (Top Module)](#️-iv-composite-filter-area-top-module)
  - [1. Button States and Left/Right Click Mutually Exclusive Logic](#1-button-states-and-leftright-click-mutually-exclusive-logic)
  - [2. Drag and Drop Sorting (Free UI Customization)](#2-drag-and-drop-sorting-free-ui-customization)
  - [3. Deep Editing of Custom Extensions](#3-deep-editing-of-custom-extensions)
  - [4. Smart Text Input](#4-smart-text-input)
- [🌳 V. Tag Tree and Visual Management (Bottom Module)](#-v-tag-tree-and-visual-management-bottom-module)
  - [1. Advanced Click Logic for Tags](#1-advanced-click-logic-for-tags)
  - [2. Powerful Drag & Drop Reorganization Mechanism](#2-powerful-drag--drop-reorganization-mechanism)
  - [3. Detailed Explanation of the "Toolbar" on the Right Side of Tag Groups](#3-detailed-explanation-of-the-toolbar-on-the-right-side-of-tag-groups)
  - [4. Ubiquitous Context Menus](#4-ubiquitous-context-menus)
- [⚠️ VI. Core Operation Precautions](#️-vi-core-operation-precautions)
- [🤖 VII. Local AI Smart Tagging: Step-by-Step Configuration Guide](#-vii-local-ai-smart-tagging-step-by-step-configuration-guide)
- [📅 Appendix: v1.2.5 Release Notes Summary](#-appendix-v125-release-notes-summary)

------

**[XYplorerTagHelper](https://github.com/C21H21NO2S/XYplorerTagHelper)** is ostensibly an open-source tag helper tool on GitHub, but in reality, it is a **full-featured Visual Search Builder for XYplorer**. It transforms complex file types, paths, remarks, and multiple tag logics into intuitive "point-and-click and drag-and-drop" actions, compiling them in real-time into XYplorer's advanced search syntax.

## 🏗️ I. Software Architecture and Underlying Logic

- **Technical Architecture:** Built on a lightweight `pywebview` architecture. The front end is a modern UI constructed purely with HTML/CSS/JS (supporting smooth dark/light dual themes), and the back end is Python. It has no heavy third-party framework dependencies throughout, ensuring extremely fast startup times and low memory usage.
- **State Machine Logic:** Every click (left/right), input, or drag you perform is stored in a global state tree. The engine parses this tree in real-time to compile boolean search syntax such as `tags:A & !B /types={:Image}`.
- **Communication Execution:** The compiled syntax is silently sent to `XYplorer.exe` via Python as a command line argument (`/feed="::goto..."`) for execution. The tag reading and writing functionality achieves two-way communication by invoking internal scripts and the system clipboard.

------

## ⚙️ II. Initial Configuration and Workspace Management (Workspace)

The software supports multi-workspace management. Data, tag tree structures, and filter states are **completely independent and do not interfere with each other** across different workspaces.

## 1. Basic Settings

- Click the **"⚙️ (Gear)"** icon in the top right corner of the interface to enter system settings.
- **XYplorer Path:** You must accurately fill in the path to XYplorer (can be the `.exe` file path or the folder it resides in), otherwise search commands cannot be sent.
- **UI Language and Theme:** Supports seamless switching between Simplified Chinese / English / Traditional Chinese and Light / Dark themes.

## 2. Advanced Workspace Operations

- **Drag and Drop Sorting:** The workspace tabs at the top support directly holding the **left mouse button and dragging left or right** to adjust the tab order as you please.
- **Rename Workspace:** After triggering a rename, the name on the top workspace tab will synchronize and update immediately without requiring a reload.
- **Workspace Import/Export:** **Right-click** on the "+" button at the far right of the tag group button bar to access the newly added "Export Current Workspace" and "Import to Current Workspace" features. Official presets or AI batch-generated tag group data can be quickly imported using this feature. *(Official preset tag groups download: [Workspace Presets](https://github.com/C21H21NO2S/XYplorerTagHelper/tree/main/Workspace))*。
- **Context Menu (Core):** **Right-click** on any workspace tab to bring up the advanced menu:
  - **Change Tab Color:** Set a dedicated theme color block for different workspaces to facilitate visual isolation.
  - **Rename / Delete:** Deleting will prompt a confirmation to prevent accidental touches. Note: The system strictly requires at least one workspace to be kept.
  - **Duplicate Workspace:** Perfectly clones all tag group structures and color configurations of the current workspace, highly suitable as an initialization template for a new project. *(Note: v1.2.5 has fixed the bug where duplicating a workspace would occasionally spawn a "ghost workspace")*.

------

## 🎛️ III. Four Core Action Buttons (Top Action Buttons)

The four large buttons located at the top of the interface are the "execution engine" of the entire tool. They are responsible for translating the visual states you build in the modern UI panel below into actual commands that XYplorer can understand.

## 1. **🔍 Search**

- **Function:** Automatically compiles all active filter conditions on the panel into XYplorer's advanced search syntax and dispatches it for execution.
- **Precautions:** Search logic strictly follows your click states on the panel: Left click (Green) represents inclusion or OR, and Right click (Red) represents exclusion (NOT).

## 2. **🏷️ Apply Tag / Remove Tag (Tag)**

- **Function:** Batch modifies the tags of the currently selected files in XYplorer. **Supports completing both "adding new tags" and "precisely erasing old tags" simultaneously in a single click**.
- **Core Operation Logic:**
  - **Left Click Highlight (Blue 🔵):** Marked for **Addition**. This tag will be written to the selected files.
  - **Right Click Highlight (Red 🔴):** Marked for **Removal**. If the selected files currently contain this tag, it will be precisely erased.
- **Smart Tagging Module (Advanced/AI):** **Right-click** the "Tag" button at the top to summon the brand-new advanced processing menu. Includes:
  - Batch Apply UCS Tags (Note: Filenames must begin with a standard UCS CatID).
  - Batch Convert Filenames to UCS Tags.
  - AI Filename matches UCS Tags (Inactive).
  - AI Filename auto-generate tags - En/Zh (Active).
  - AI Filename auto-generate tags (Active).
  - AI Text content auto-generate tags (Active).
- **Precautions:** You must ensure that XYplorer is the active window and that at least one file is selected.

## 3. **📖 Read Tags (Read)**

- **Function:** Extracts the existing tags of the currently selected files in XYplorer, and automatically highlights, categorizes, and expands the corresponding tag tree hierarchy in the helper panel.

## 4. **🗑️ Clear**

- **Function:** One-click state reset. Instantly clears all highlight states (Green, Red, Blue) in the composite filter area and tag tree, empties all text input boxes, and restores the workspace to its initial standby state.

------

## 🎛️ IV. Composite Filter Area (Top Module)

This is the core area for building filter conditions such as file types, paths, names, remarks, etc.

## 1. Button States and Left/Right Click Mutually Exclusive Logic

- **Left Click (Include / OR):** Button turns **Green** 🟢. Indicates this condition is included when searching.
- **Right Click (Exclude / NOT):** Button turns **Red** 🔴. Indicates this condition is excluded when searching.

## 2. Drag and Drop Sorting (Free UI Customization)

- **Type and Extension Sorting:** Hold down preset type buttons or custom extension buttons, and **drag left or right** to adjust their display order.
- **Labels Sorting:** After syncing XYplorer labels, you can also drag left or right to rearrange the order of label colors.

## 3. Deep Editing of Custom Extensions

- **Batch Add (Right Click):** **Right-click on the "➕ (Plus)" button** on the right side of the custom extension area to summon the batch add menu.
- **Edit Mode:** Click the **"✏️ (Pencil)"** icon inside the panel to enter extension edit mode (left click to rename, click the red X in the top right corner to delete).

## 4. Smart Text Input

- **Path/Name/Remark:** Supports smart composite logic. Typing `A+B,C-D` in the input box will be automatically converted by the engine into strict XYplorer syntax: `(A and B) or (C and not D)`.
- **Syntax Improvements:** The latest version supports directly searching for tags containing the "&" symbol; the underlying layer has been deeply optimized to avoid conflicts with complex boolean logic symbols like AND/OR/NOT, &, |, and quotes (").

------

## 🌳 V. Tag Tree and Visual Management (Bottom Module)

This is the core workflow area for managing tag categories, applying tags, and reading tags.

## 1. Advanced Click Logic for Tags

- **Left Click:** Turns **Blue** 🔵 (Must include this tag).
- **Right Click:** Turns **Red** 🔴 (Must exclude this tag).
- **Middle Click:** Turns **Green** 🟢 (OR logic, as long as it contains any one of the multiple blue tags).
- **Quick Rename:** You can now use **Alt + Middle Click** on a tag or tag group to quickly rename it.
- **Alias and Remark System:** Hovering the mouse over a tag will display alias/remark/description hints. Use **Ctrl + Middle Click** to quickly set translation or remark information.

## 2. Powerful Drag & Drop Reorganization Mechanism

- **Tag Transfer:** Drag a tag button and drop it into the dashed box area of another group.
- **Group Rearrangement and Parent-Child Hierarchy Conversion:** Drag the "Group Name" area and judge the drop point based on the **highlighted indicator line** (Yellow line above, Yellow line below, or full row background highlight to make it a child group).

## 3. Detailed Explanation of the "Toolbar" on the Right Side of Tag Groups

- **Search Tags:** Added a tag search system supporting searches for tag groups, the tags themselves, remarks, and descriptions. The system will independently remember the last search query and mode (exact/fuzzy) for each workspace.
- **🧹 Clear:** One-click to clear the highlighted activation state of all tags in the tree diagram.
- **↕️ Expand/Collapse All:** Click to control the overall collapse state. Now supports shortcuts: **Alt + Left Click** to force expand all groups; **Alt + Right Click** to force collapse all groups. The system will automatically remember your previous expand/collapse state.
- **⏺ Solid Circle / ⭕ Outline Circle:** Locate activated groups and Focus Mode (hides inactive groups).
- **Toggle Display Alias/Remark:** Added a button to toggle the alias/remark display on the interface with one click, supporting independent memory of the previous state per workspace.
- **Enable/Disable Hover Tooltip:** Toggle whether the hover tooltip box is displayed, also supporting independent workspace memory.

## 4. Ubiquitous Context Menus

- **Group Name Context Menu:** Allows you to change category colors, batch create subgroups, and cross-region transfer (move/copy to other workspaces).
- **Batch State Control:** Added quick state options in the group name context menu to allow one-click "Select all tags in group (OR)", "Exclude all tags in group (NOT)", and "Clear group state".

------

## ⚠️ VI. Core Operation Precautions

1. **Prerequisite for Tagging:** Before using the "Apply Tag" function, please ensure XYplorer is the active window and **at least one file is selected**. If no file is selected, XYplorer will ignore the tag command.
2. **Clipboard Limitations for Reading Tags:** If reading a massive number of files at once with highly complex tags (exceeding 500 characters), the software will pop up a "Batch Confirmation Window" to prevent misoperation.
3. **System Data Security:** All configuration and tag data are saved in `.json` format under the `Data` folder in the software directory. Before performing large-scale structural rearrangements, it is recommended to manually back up using "Export Workspace Data".

------

## 🤖 VII. Local AI Smart Tagging: Step-by-Step Configuration Guide

By integrating a local Large Language Model (LLM), XYplorerTagHelper can automatically extract precise tags based on the "filename" or "file content" and automatically translate them into a language consistent with the software interface. The entire process runs **purely locally**, requires no internet connection, consumes zero API fees, and absolutely protects your file privacy!

## 💡 1. Model Recommendation Guide

- 🥇 **Top Recommendation: `qwen2.5:3b`**

  The perfect balance of speed and precision! It can highly accurately understand long filenames, provide authentic translations, and generates at extremely fast speeds, making it the best choice for daily use.

- 🥈 **Low-spec Alternative: `qwen2.5:1.5b`**

  Extremely lightweight, taking up very little memory (around 1GB). Ideal for older computers or those with tight RAM, outputs words instantly.

- ⚠️ **Special Note: `qwen3:1.7b`**

  As a new-generation model, its instruction-following capability is very strong, but in current local API tests, its generation speed is slightly slower than version 2.5. If you pursue the latest tech, you may download and test it yourself.

## 🚀 2. Installation and Configuration Steps (Only 3 Steps)

**Step 1: Install the Local AI Engine (Ollama)**

1. Visit the official Ollama website: https://ollama.com/.
2. Download the Windows version and double-click to install.
3. Once installed, an "alpaca" icon will appear in your taskbar, indicating the engine is running in the background.

**Step 2: Download the AI Model**

1. Press `Win + R` in Windows, type `cmd`, and press Enter to open the command prompt window.
2. Enter the command and press Enter to begin downloading (using the top recommended model as an example): `ollama run qwen2.5:3b`.
3. When the download is complete, `>>>` will appear. You can type "Hello" to test it. Once the test is successful, simply close the black window (Ollama will serve silently in the background).

**Step 3: Bind AI in XYplorerTagHelper**

1. Open the `XYplorerTagHelper` software, and click the ⚙️ **Settings button** in the top right corner.
2. Locate the **AI Module Settings** area:
   - **AI API URL (Ollama):** Change to `http://127.0.0.1:11434/api/generate` or `http://localhost:11434/api/generate`.
   - **AI Model Name:** Fill in the exact name you downloaded, for example: `qwen2.5:3b`.
3. Click **"Save Settings"**.

## 🎉 3. How to Use AI Smart Tagging?

1. Select the files you need to tag in XYplorer (supports batch selecting multiple files).
2. In `XYplorerTagHelper`, **right-click** the **"Tag"** button at the top.
3. In the pop-up menu, select the AI-exclusive options with the orange icons:
   - 🧠 **AI Filename matches UCS Tags (No Active):** Strictly selects the most appropriate words from the left-side dictionary to apply to the file.
   - 🧠 **AI Filename auto-generate tags - En/Zh (Active):** AI freely extracts tags, provides bilingual remarks in English and Chinese, and automatically activates and categorizes them into the current tag group.
   - 🧠 **AI Filename auto-generate tags (Active):** AI extracts tags based on the filename, automatically translates (controlled by the interface language), and activates/categorizes them.
   - 🧠 **AI Text content auto-generate tags (Active):** Specifically for text files, AI reads the beginning of the document to extract core tags.
4. After clicking, the bottom right corner will prompt "AI is thinking...", quietly wait for the AI to finish tagging massive amounts of files!

------

## 📅 Appendix: v1.2.5 Release Notes Summary

- **Added:** Workspace import/export functionality, tag group batch select all/exclude/clear state, Alt+Left/Right click global expand/collapse, Alt+Middle click quick rename, Ctrl+Middle click alias/remark/description system and display toggle controls.
- **Enhanced:** Memorized multi-dimensional tag search system, introduced UCS (Universal Category System) and local AI large model smart tagging menu.
- **Optimized:** Automatically remembers tag group expansion states, seamlessly refreshes workspace UI renaming, improved compatibility conflicts for the "&" symbol in complex boolean logic searches, and fixed the bug where ghost tabs appeared when duplicating workspaces.
