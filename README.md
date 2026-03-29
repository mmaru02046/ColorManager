# Color Library Manager / 色卡管理器

Color Library Manager is a local desktop tool for managing scientific color palettes.

色卡管理器是一个面向科研绘图场景的本地桌面工具，用来整理、预览、拼配和导出色卡。

## Overview / 简介

This project focuses on a practical workflow:

本项目重点解决的是科研配色中的实际工作流：

- Browse palette files visually instead of reading file names only.
- Preview colors, gradients, and extracted image palettes directly.
- Build a working palette by drag-and-drop.
- Check colors with normal, colorblind, and grayscale chart previews.
- Export palettes to formats used by OriginLab, R, Python, and MATLAB.

- 不只是看文件名，而是直接可视化浏览色卡。
- 直接预览颜色、渐变和图片提取结果。
- 通过拖拽建立自己的工作色卡。
- 在正常、色盲、灰度图表预览下检查颜色是否可用。
- 导出到 OriginLab、R、Python、MATLAB 等常用格式。

## Current Features / 当前功能

- Import `ASE`, `CSV`, `JSON`, `GPL`, `PAL`, and image files.
- Scan `materials` and `library` folders.
- Folder tree browsing with filters for format, hue, count, favorites, and tags.
- Palette detail view with swatches, image preview, and gradient preview.
- Cart area with drag sorting, multi-select removal, and export.
- Scientific chart preview: `Line`, `Bar`, `Scatter`.
- Preview modes: `Normal`, `Colorblind`, `Grayscale`.
- Colorblind types: `Protan`, `Deutan`, `Tritan`.
- Color lab tools: `Similar`, `Complement`, `Blend Mid`, `Diverging`, `Tint Ramp`.
- Export to `ASE`, `CSV`, `JSON`, `PAL`, and code snippets for `R`, `Python`, `MATLAB`.

- 支持导入 `ASE`、`CSV`、`JSON`、`GPL`、`PAL` 和图片文件。
- 支持扫描 `materials` 和 `library` 目录。
- 左侧支持文件夹树、格式、色系、颜色数量、收藏、标签筛选。
- 中间支持颜色卡、图片原图、渐变条预览。
- 右侧拼配区支持拖拽排序、多选删除、保存导出。
- 支持科研图表预览：`Line`、`Bar`、`Scatter`。
- 支持预览模式：`Normal`、`Colorblind`、`Grayscale`。
- 支持色盲类型：`Protan`、`Deutan`、`Tritan`。
- 支持选色工作台：`Similar`、`Complement`、`Blend Mid`、`Diverging`、`Tint Ramp`。
- 支持导出 `ASE`、`CSV`、`JSON`、`PAL`，以及 `R`、`Python`、`MATLAB` 代码片段。

## Project Structure / 项目结构

```text
Color/
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ models.py
│  ├─ parsers.py
│  ├─ storage.py
│  └─ ui/
│     └─ main_window.py
├─ icon.ico
└─ README.md
```

## Run From Source / 源码运行

Requirements:

运行前提：

- Python 3.11 recommended
- `PySide6`

Start the app from the project root:

在项目根目录运行：

```bash
python app/main.py
```

## Typical Workflow / 典型使用流程

1. Set `materials` and `library` folders.
2. Import palette files or images.
3. Browse palettes on the left.
4. Preview and pick colors in the center panel.
5. Add colors to the cart on the right.
6. Reorder colors by drag-and-drop.
7. Check chart preview in normal, colorblind, and grayscale modes.
8. Save or export the final palette.

1. 设置 `materials` 和 `library` 目录。
2. 导入色卡文件或图片。
3. 在左侧浏览色卡。
4. 在中间预览并挑选颜色。
5. 将颜色加入右侧拼配区。
6. 通过拖拽调整顺序。
7. 在正常、色盲、灰度模式下检查图表预览。
8. 保存或导出最终色卡。

## Status / 当前状态

This project is already usable for daily scientific palette management, but it is still under active iteration.

这个项目已经可以用于日常科研配色管理，但仍在持续迭代中。

Possible future improvements:

后续可能继续补充：

- better palette-grid detection from images
- stronger accessibility checks
- more color interpolation and harmony modes
- cleaner release workflow

- 更完整的图片色卡识别
- 更严格的可访问性检查
- 更多插值与配色模式
- 更完善的发布流程

## License / 许可

License not decided yet.

许可协议暂未确定。
