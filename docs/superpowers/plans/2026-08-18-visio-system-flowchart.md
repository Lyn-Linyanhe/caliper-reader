# Visio System Flowchart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a simple black-and-white, natively editable Visio flowchart that reflects the current caliper-reading pipeline and export it as vector files.

**Architecture:** Use Visio COM on Windows to create one landscape page from native rectangles, text, and arrow connectors. The main path covers image input, ROI localization, orientation correction/preprocessing, region separation, two parallel readers, reading fusion, and output; no reference raster is embedded.

**Tech Stack:** PowerShell, Microsoft Visio COM, Visio SVG/PDF export, package inspection with .NET ZIP APIs.

**Spec:** Current project pipeline documented in `README.md` and implemented under `caliper/`; existing `图01_系统流程图.png` is a layout reference only.

## Global Constraints

- Final editable source must be `.vsdx` with native Visio shapes and editable text.
- Diagram style must be simple black-and-white wireframe with black arrows and no decorative color fills.
- Existing PNG and unrelated user files must not be overwritten.
- Deliver vector exports (`.svg` and `.pdf`); do not use PNG as a deliverable.
- Verify the saved package has no embedded full-page raster reference image.

### Task 1: Build the native Visio flowchart

**Files:**
- Create: `tools/create_visio_system_flowchart.ps1`
- Create: `paper/03_排版与审校/论文图表素材/论文插图/图01_系统流程图_visio.vsdx`

- [x] **Step 1: Create the COM drawing script**

  Define coordinate helpers and draw only native rectangles, text boxes, and line connectors. Use a single landscape page with a title, a five-stage preparation path, two parallel recognition boxes, a fusion box, and an output box. Keep all fills white, borders black, and text black.

- [x] **Step 2: Run the script and save the editable source**

  Run PowerShell with `-ExecutionPolicy Bypass`; check that Visio COM opens, saves the target `.vsdx`, and closes cleanly.

### Task 2: Export vector deliverables and inspect editability

**Files:**
- Create: `paper/03_排版与审校/论文图表素材/论文插图/图01_系统流程图_visio.svg`
- Create: `paper/03_排版与审校/论文图表素材/论文插图/图01_系统流程图_visio.pdf`

- [x] **Step 1: Export SVG and PDF from the saved VSDX**

  Use the Visio page export APIs after saving the source document; do not export from the old PNG.

- [x] **Step 2: Inspect the package and outputs**

  Confirm the `.vsdx` contains a nonzero native shape count, no `visio/media` full-page raster, and that SVG/PDF are non-empty.

- [x] **Step 3: Render/check the vector preview**

  Open the SVG as the visual preview and check reading order, arrow connections, text fit, and absence of overlap. Report the source and vector paths to the user.
