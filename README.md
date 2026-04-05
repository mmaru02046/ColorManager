# ColorManager / 色卡管理器

ColorManager is a local desktop tool for collecting, previewing, organizing, and exporting scientific color palettes.

色卡管理器是一个面向科研绘图场景的本地桌面工具，用来整理、预览、拼配、检查和导出色卡。

## Overview / 项目定位

This project is built around a practical workflow for scientific plotting:

本项目围绕科研绘图中的实际配色流程而设计：

- browse palette assets visually instead of only reading file names
- collect colors from `ASE`, gradients, images, and PDF figures
- build a working palette in a cart-like area
- preview how colors behave in common scientific plots
- export palettes for OriginLab, R, Python, and MATLAB

- 不只是按文件名找色卡，而是直接可视化浏览素材
- 从 `ASE`、渐变、图片、PDF 图页中提取颜色
- 在右侧拼配区整理自己的工作色卡
- 提前检查颜色在常见科研图中的表现
- 导出给 OriginLab、R、Python、MATLAB 等工具使用

## Highlights / 功能速览

| Area | What it supports |
| --- | --- |
| Palette sources | `ASE`, `CSV`, `JSON`, `GPL`, `PAL`, images, `PDF` |
| Browsing | folder tree, filters, favorites, tags |
| Extraction | image click/region picking, PDF page and region extraction |
| Editing | cart sorting, multi-select, palette generation |
| Preview | `Line`, `Bar`, `Scatter`, `Clustered`, `Circular`, `Map` |
| Accessibility check | `Normal`, `Colorblind`, `Grayscale` |
| Export | `ASE`, `CSV`, `JSON`, `PAL`, `R`, `Python`, `MATLAB` snippets |

| 模块 | 支持内容 |
| --- | --- |
| 色卡来源 | `ASE`、`CSV`、`JSON`、`GPL`、`PAL`、图片、`PDF` |
| 浏览方式 | 文件夹树、筛选、收藏、标签 |
| 取色方式 | 图片点击/框选、PDF 页面与区域提取 |
| 编辑能力 | 拼配区排序、多选、配色生成 |
| 预览类型 | `Line`、`Bar`、`Scatter`、`Clustered`、`Circular`、`Map` |
| 检查模式 | `Normal`、`Colorblind`、`Grayscale` |
| 导出方式 | `ASE`、`CSV`、`JSON`、`PAL`、`R`、`Python`、`MATLAB` 代码片段 |

## Main Features / 主要功能

- Import palette files, gradients, images, and PDF sources
- Browse `materials` and `library` with folder tree, filters, favorites, and tags
- Preview palette colors, gradients, source images, and PDF pages
- Extract colors from images and PDF pages by click or region selection
- Build palettes in the cart with drag sorting and multi-select editing
- Generate related colors with `Similar`, `Complement`, `Blend Mid`, `Diverging`, and `Tint Ramp`
- Use quick plot preview for daily checks and `Advanced Preview` for more complex plot styles
- Export palettes to common scientific workflows and reusable code snippets

- 支持导入色卡文件、渐变、图片和 PDF 素材
- 支持以文件夹树、筛选、收藏、标签方式浏览 `materials` 和 `library`
- 支持预览色卡颜色、渐变条、原图和 PDF 页面
- 支持从图片和 PDF 页面中通过点击或框选提取颜色
- 支持在右侧拼配区拖拽排序、多选编辑、整理工作色卡
- 支持 `Similar`、`Complement`、`Blend Mid`、`Diverging`、`Tint Ramp` 等配色辅助
- 支持日常快速预览和独立的 `Advanced Preview` 高级示意图
- 支持导出到常见科研工作流以及可复用代码片段

## Map Note / 地图说明

The China map used in preview is a simplified display asset. For presentation purposes, the original source data has been adjusted and the nine-dash line is not shown in the current preview.

预览中使用的中国地图为简化展示素材。出于界面展示需要，当前预览未显示原始数据中的九段线。
## Interaction Notes / 交互细节提示

A few palette-generation actions behave differently depending on selection:

有几类配色生成动作会根据当前是否选中颜色，采用不同逻辑：

- If colors are selected in the cart, `Blend Mid` and `Diverging` insert new colors between the selected colors.
- If nothing is selected, generated colors are appended to the end of the cart.
- `Advanced Preview` uses the cart order directly.
- `PDF Extractor` keeps a temporary preview palette first; you can then add that preview to the main cart or save it into `materials`.

- 如果右侧拼配区有选中的颜色，`Blend Mid` 和 `Diverging` 会把新颜色插入到这些已选颜色之间。
- 如果右侧没有选中颜色，生成结果会直接追加到拼配区末尾。
- `Advanced Preview` 会直接使用右侧拼配区当前顺序。
- `PDF Extractor` 会先生成临时预览色卡，再由你决定加入主拼配区或保存到 `materials`。

## Project Structure / 项目结构

```text
Color/
├─ app/
│  ├─ assets/
│  ├─ main.py
│  ├─ config.py
│  ├─ models.py
│  ├─ parsers.py
│  ├─ storage.py
│  └─ ui/
│     ├─ main_window.py
│     └─ pdf_dialog.py
├─ icon.ico
├─ build_exe.py
└─ README.md
```

## Run From Source / 源码运行

Recommended environment:

建议环境：

- Python 3.11
- `PySide6`

Run from the project root:

在项目根目录运行：

```bash
python app/main.py
```

## Typical Workflow / 典型使用流程

1. Choose `materials` and `library` folders.
2. Import palette files, images, or PDF sources.
3. Browse palettes on the left and inspect details in the center.
4. Add useful colors to the cart on the right.
5. Reorder, edit, and generate supporting colors.
6. Check preview behavior in normal, colorblind, and grayscale modes.
7. Save or export the final palette.

1. 选择 `materials` 和 `library` 目录。
2. 导入色卡文件、图片或 PDF 素材。
3. 在左侧浏览素材，在中间查看详情。
4. 把需要的颜色加入右侧拼配区。
5. 调整顺序，补充或生成配色。
6. 在正常、色盲、灰度模式下检查预览效果。
7. 保存或导出最终色卡。

## Current Scope / 当前状态

The app is already usable for day-to-day scientific palette management, and it is still actively evolving.

这个项目已经可以用于日常科研配色管理，并且仍在持续迭代中。

Current focus:

当前重点包括：

- scientific palette management
- image and PDF color extraction
- plot-oriented preview and export workflow

- 科研配色素材管理
- 图片和 PDF 取色
- 面向科研图表的预览与导出流程

## License / 许可

This project is intended for personal, academic, research, and other non-commercial use.
Commercial use is not permitted without explicit permission from the author.

本项目面向个人、学习、科研及其他非商业用途。
任何商业使用均需事先获得作者明确许可。

License file:

许可文件：

- `PolyForm Noncommercial 1.0.0`
- see [LICENSE](LICENSE)


