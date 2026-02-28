# XYplorerTagHelper User Guide

## Table of Contents
- [🏗️ I. Software Architecture & Underlying Logic](#️-i-software-architecture--underlying-logic)
- [⚙️ II. Initial Configuration & Workspace Management](#️-ii-initial-configuration--workspace-management)
  - [1. Basic Settings](#1-basic-settings)
  - [2. Advanced Workspace Operations](#2-advanced-workspace-operations)
- [🎛️ III. Four Core Action Buttons (Top Action Buttons)](#️-iii-four-core-action-buttons-top-action-buttons)
  - [1. 🔍 Search](#1--search)
  - [2. 🏷️ Tag / Untag](#2-️-tag--untag)
  - [3. 📖 Read Tags](#3--read-tags)
  - [4. 🗑️ Clear](#4-️-clear)
- [🎛️ IV. Composite Filter Area (Top Module)](#️-iv-composite-filter-area-top-module)
  - [1. Button States & L/R Click Mutex Logic](#1-button-states--lr-click-mutex-logic)
  - [2. Drag-and-Drop Sorting (Custom UI)](#2-drag-and-drop-sorting-custom-ui)
  - [3. Deep Editing of Custom Extensions](#3-deep-editing-of-custom-extensions)
  - [4. Smart Text Input](#4-smart-text-input)
- [🌳 V. Tag Tree & Visual Management (Bottom Module)](#-v-tag-tree--visual-management-bottom-module)
  - [1. Advanced Tag Selection Logic](#1-advanced-tag-selection-logic)
  - [2. Powerful Drag & Drop Reorganization](#2-powerful-drag--drop-reorganization)
  - [3. Toolbar on the Right of Tag Groups](#3-toolbar-on-the-right-of-tag-groups)
  - [4. Omnipresent Right-Click Menus](#4-omnipresent-right-click-menus)
- [⚠️ VI. Core Operation Precautions](#️-vi-core-operation-precautions)

---

[**XYplorerTagHelper**](https://github.com/C21H21NO2S/XYplorerTagHelper) appears to be an open-source tagging assistant on GitHub, but it is actually a **full-featured Visual Search Builder for XYplorer**. It translates complex file types, paths, comments, and multi-tag logic into intuitive "point, click, and drag" operations, compiling them in real-time into XYplorer's advanced search syntax.

## 🏗️ I. Software Architecture & Underlying Logic

* **Technical Architecture:** Adopts a lightweight `pywebview` architecture. The frontend is a modern UI built with pure HTML/CSS/JS (supporting smooth dark/light dual themes), while the backend is Python. It has zero dependency on large third-party frameworks, ensuring extremely fast startup and low memory usage.
* **State Machine Logic:** Every click (left/right), input, and drag is stored in a global state tree. The engine parses this tree in real-time to compile boolean search syntax, such as `tags:A & !B /types={:Image}`.
* **Communication & Execution:** The compiled syntax is silently sent via Python to `XYplorer.exe` as a command line execution (`/feed="::goto..."`). Reading and writing tags are achieved through two-way communication using internal scripts and the system clipboard.

---

## ⚙️ II. Initial Configuration & Workspace Management

The software supports multi-workspace management. Data, tag tree structures, and filter states are **completely independent and do not interfere with each other** across different workspaces.

### 1. Basic Settings

* Click the **"⚙️ (Gear)"** icon in the top right corner of the interface to enter system settings.
* **XYplorer Path:** You must accurately enter the path to XYplorer (either the `.exe` file path or its folder); otherwise, search commands cannot be sent.
* **UI Language & Theme:** Supports seamless switching between English/Simplified Chinese/Traditional Chinese and light/dark themes.

### 2. Advanced Workspace Operations

* **Drag-and-Drop Sorting:** The workspace tabs at the top can be directly dragged left or right with the **left mouse button** to arrange their order as desired.
* **Right-Click Menu (Core):** **Right-click** on any workspace tab to bring up the advanced menu:
  * **Modify Tab Color:** Set an exclusive theme color block for different workspaces for easy visual separation.
  * **Rename / Delete:** Deletion includes an anti-accidental touch confirmation. Note: The system strictly requires at least one workspace to be retained.
  * **Duplicate Workspace:** Perfectly clones all tag group structures and color configurations of the current workspace, making it ideal as an initialization template for new projects.

---

## 🎛️ III. Four Core Action Buttons (Top Action Buttons)

The four large buttons at the top of the interface are the "execution engine" of the tool. They translate the visual state you built in the modern UI panel below into actual commands that XYplorer understands.

### 1. **🔍 Search**

* **Function:** Automatically compiles all active filter conditions on the panel (including file types, custom extensions, paths, advanced composite tags, etc.) into XYplorer's advanced search syntax, and dispatches it to execute a full-disk or specific-directory search.
* **Note:** The search logic strictly follows your click states on the panel: Left-click (Green) means include/OR, Right-click (Red) means exclude/NOT. After every successful search, the system automatically saves your inputted path, name, and comments into the history dropdown menus.

### 2. **🏷️ Tag / Untag**

* **Function:** Batch modify tags of the currently selected files in XYplorer. **Supports simultaneously completing "adding new tags" and "precisely erasing old tags" in a single click.**
* **Core Operation Logic:**
  * **Left-click Highlight (Blue 🔵):** Marked for **Addition**. This tag will be written to the selected files.
  * **Right-click Highlight (Red 🔴):** Marked for **Removal**. If the selected files currently contain this tag, it will be precisely erased.
* **Note:** * The underlying engine intelligently prioritizes "Remove" commands before executing "Add" commands.
  * Before clicking, **you must ensure XYplorer is the active window and at least one file is selected**. If no files are selected, or if there are no active Blue/Red tags on the interface (e.g., only Green 🟢 highlighted by middle-click), the system will block the operation and pop up an error prompt.

### 3. **📖 Read Tags**

* **Function:** Extracts existing tags from the currently selected file in XYplorer, and automatically highlights, categorizes, and expands the corresponding tag tree hierarchy in the helper panel.
* **Note:** This function uses the system clipboard for data transfer. If the read tag text is extremely large (e.g., over 500 characters or containing multiple lines of abnormal text), the system will pop up a safety confirmation window to prevent massive erroneous activations, allowing you to preview and manually confirm before writing to the UI.

### 4. **🗑️ Clear**

* **Function:** One-click state reset. Instantly clears all highlight states (Green, Red, Blue) in the composite filter area and tag tree, empties all text input boxes, and restores the workspace to its initial standby state.
* **Note:** This operation only clears the **search filter conditions on the current interface**; it will absolutely NOT delete any of your group names, tag configurations, or workspace history data, nor will it affect the real file tags in XYplorer.

---

## 🎛️ IV. Composite Filter Area (Top Module)

This is the core area for building filter conditions like file types, paths, names, and comments.

### 1. Button States & L/R Click Mutex Logic

In panels like "Types", "Custom Ext.", and "Rating", the button operation logic is highly rigorous:

* **Left-click (Include / OR):** Button turns **Green** 🟢. Indicates the condition is included in the search. *Note: Left-click activation features smart mutex, automatically canceling all excluded (Red) states under the same category.*
* **Right-click (Exclude / NOT):** Button turns **Red** 🔴. Indicates the condition is excluded from the search. *Note: Right-click exclusion forces the clearing of all active (Green) states under that category.*

### 2. Drag-and-Drop Sorting (Custom UI)

The composite area panels highly support customization:

* **Types and Extensions Sorting:** Click and hold preset type buttons like "Text", "Image", or your own custom extension buttons, and **drag left/right** to adjust their arrangement order on the interface.
* **Labels Sorting:** After clicking "Sync XYplorer Labels" to fetch configurations, it also supports left/right dragging to rearrange the order of label colors.

### 3. Deep Editing of Custom Extensions

* **Batch Add (Right-click):** **Right-click on the "➕ (Plus)" button** on the right side of the custom extensions area to bring up the batch add menu, allowing one-click import of common extensions (like Images, Documents) or pasting a custom list.
* **Edit Mode:** Click the **"✏️ (Pencil)"** icon in the panel to enter extension edit mode.
  * **Rename:** **Left-click** any extension button to pop up an input box; modify and hit Enter.
  * **Delete:** Click the red **"X"** in the top right corner of the button to delete.
  * *(Note: Please click the pencil icon again to exit after modifications are complete; otherwise, normal left/right click filtering operations cannot be performed)*

### 4. Smart Text Input

* **Path/Name/Comment:** Supports smart composite logic. Typing `A+B,C-D` in the input box will automatically be converted by the engine into strict XYplorer syntax: `(A AND B) OR (C AND NOT D)`.

---

## 🌳 V. Tag Tree & Visual Management (Bottom Module)

This is the core workflow area for managing tag categories, tagging, and reading tags.

### 1. Advanced Tag Selection Logic

* **Left-click:** Turns **Blue** 🔵 (MUST contain this tag).
* **Right-click:** Turns **Red** 🔴 (MUST exclude this tag).
* **Middle-click:** Turns **Green** 🟢 (OR logic, as long as it contains any one of the multiple blue tags).

### 2. Powerful Drag & Drop Reorganization

The entire tag tree supports free drag-and-drop rearrangement and hierarchy modification just like a file manager:

* **Tag Button Dragging:** Click and hold a tag button, drag it into the dashed box area of another group and release it to **transfer the tag to the new group**.
* **Group Rearrangement & Parent-Child Hierarchy Conversion:** Click and hold the "Group Name" area (Header) of a group and drag. Pay attention to the **highlight prompt lines** of the target group:
  * **Top Solid Yellow Line:** Places it as the **previous sibling group** of the target.
  * **Bottom Solid Yellow Line:** Places it as the **next sibling group** of the target.
  * **Full Row Background Highlight (Center):** Places it **inside** the target group, making it a **subgroup** of the target.
  * *(Note: The "Uncategorized" group in the root directory is protected by the system and cannot be dragged and converted into a subgroup)*

### 3. Toolbar on the Right of Tag Groups

On the right side of the text "🏷️ Tag Groups", there is a row of view-control artifacts:

* **🧹 Clear:** One-click clear of all highlighted active states of tags in the tree.
* **↕️ Expand/Collapse All:** One-click control of the overall collapse state of the tag tree.
* **⏺ Solid Circle (Expand Active Only):** Intelligently collapses irrelevant groups, forces expansion, and **tracks and locates** the path of the group where tags are currently highlighted and active.
* **⭕ Hollow Circle (Focus Mode):** Directly **hides** all inactive groups, instantly refreshing the interface to show only the operating context.
* **✏️ Pencil (Edit Mode):** Once entered, **left-click** a group name or tag to directly rename it; click the red X to delete.
* **➕ Plus Sign (New Root Group):** Left-click to create a single root group; **right-click** to paste multi-line text to batch generate multiple root groups.
* **⌨ Mouse & Keyboard Interaction:** **Alt + Left-click** on a group name: Expand subgroups; **Alt + Right-click** on a group name: Collapse subgroups; **Alt + Middle-click** on a group name or tag: Rename.

### 4. Omnipresent Right-Click Menus

* **Top Four Operation Buttons (Search/Tag/Read/Clear):** **Right-click** to customize the background colors of these four core buttons, creating your preferred visual focus.
* **Group Name Right-Click Menu:** Right-click on any group name:
  * **Modify Category Color:** Set the background color for that group.
  * **Batch Create Subgroups:** Paste multi-line text to generate tree-like child nodes in one click.
  * **Cross-Workspace Transfer:** Select "Move to Workspace" or "Copy to Workspace" to uproot the group and all its subgroups/tags and transfer them to another workspace.

---

## ⚠️ VI. Core Operation Precautions

1. **Prerequisite for Tagging:** Before using the "Tag" function, please ensure XYplorer is active and **at least one file is selected**. If no file is selected, XYplorer will ignore the tag command.
2. **Clipboard Limits for Reading Tags:** The "Read Tags" function works by copying the file's tags to the clipboard. If a huge number of files are read at once and the tags are extremely complex (over 500 characters), the software will pop up a "Batch Confirmation Window" to prevent misoperation, allowing you to manually confirm the read tag details before executing activation.
3. **System Data Security:** All configurations and tag data are saved in ` .json` format in the `Data` folder of the software directory. Although the software has a built-in debounce auto-save mechanism, it is recommended to use **"Export Workspace Data"** in "⚙️ Settings" for manual backup before performing large-scale structural rearrangements (large-scale drag-and-drop, batch renaming).
