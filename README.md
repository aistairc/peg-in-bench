# Peg-in-Bench Scenario Generator

A Python-based tool for generating randomized assembly scenarios for a peg-in-hole benchmarking platform. This tool creates detailed task specifications with customizable pieces, tolerances, and orientations.

## Overview

The Peg-in-Bench system is designed to evaluate robotic and human assembly capabilities using modular puzzle-like pieces. The scenario generator creates randomized yet reproducible test scenarios with varying difficulty levels based on shape complexity, tolerance requirements, and piece orientations.

## Quick Start

### Prerequisites
- Python 3.7+
- PIL/Pillow (for image handling, optional)

### Installation

```bash
cd scripts
python Generate_Scenario.py --help
```

## Usage

### Basic Scenario Generation

Generate a random scenario with default settings:
```bash
python Generate_Scenario.py
```

### With Seed (Reproducible Scenarios)

Generate the same scenario repeatedly:
```bash
python Generate_Scenario.py --seed 12345
```

### With Custom Output

Save scenario to a specific file:
```bash
python Generate_Scenario.py --output my_scenario.json
```

### With Image Directory

Specify custom location for piece images:
```bash
python Generate_Scenario.py --image-dir /path/to/Photos
```

### Advanced Options

```bash
python Generate_Scenario.py \
  --seed 12345 \
  --output scenario.json \
  --image-dir Photos \
  --json-output
```

## Configuration

### Key Parameters in Code

**Shapes** (5 types):
- `triangle` - Basic triangular peg
- `rectangle` - Rectangular peg
- `circle` - Circular peg
- `hexagon` - Hexagonal peg
- `L-shape` - L-shaped connector

**Tolerances** (3 levels):
- `0.1 mm` - Tight tolerance (high difficulty)
- `1 mm` - Medium tolerance
- `3 mm` - Loose tolerance (low difficulty)

**Orientations** (8 possible):
- `0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°`
- Diagonal (45°) orientations use separate image set from `Photos_45` folder

**Base Pieces** (for assembly scaffolding):
- `base` - Simple platform (4 connection ports)
- `corner-base` - Corner connector (2 ports)
- `line-base` - Linear connector (2 ports)
- `cross-base` - Cross junction (1 port)

## Output Format

Scenarios are generated as JSON files containing:

```json
{
  "scenario_seed": 123456,
  "difficulty_level": "medium",
  "tasks": [
    {
      "task_id": "task_1",
      "type": "insertion",
      "target_shape": "circle",
      "tolerance": "1 mm",
      "orientation": "90°",
      "grid_position": "top-left"
    }
  ],
  "pieces_required": [
    {
      "id": "piece_1",
      "shape": "circle",
      "tolerance": "1 mm",
      "count": 1
    }
  ]
}
```

## STL Files Directory Structure

The `STL Files/` folder contains 3D models for 3D printing and CAD:

### Directory Organization

```
STL Files/
├── Additional pieces/          # Supplementary connector pieces
│   └── Various connector models
├── Bases/                      # Foundation/platform pieces
│   ├── base.stl
│   ├── corner-base.stl
│   ├── line-base.stl
│   └── cross-base.stl
├── Pegs/                       # Peg/hole inserts
│   ├── circle/
│   ├── triangle/
│   ├── rectangle/
│   ├── hexagon/
│   └── L-shape/
└── Shaped-holes/              # Receiving cavity pieces
    ├── 0.1mm/                 # Tight tolerance cavities
    │   ├── circle_0.1mm.stl
    │   ├── triangle_0.1mm.stl
    │   ├── rectangle_0.1mm.stl
    │   ├── hexagon_0.1mm.stl
    │   └── L-shape_0.1mm.stl
    ├── 1mm/                   # Medium tolerance cavities
    │   └── [Shape files]
    └── 3mm/                   # Loose tolerance cavities
        └── [Shape files]
```

### STL File Descriptions

**Bases**
- Foundation pieces that hold pegs or act as assembly anchors
- Each base has connection ports that match other pieces
- Used to create fixed or semi-fixed assembly scaffolds

**Pegs** (Insertable pieces)
- 5 different shapes: circle, triangle, rectangle, hexagon, L-shape
- Available in various sizes and orientations
- Can be rotated (0°, 90°, 180°, 270°, 45°, 135°, 225°, 315°)

**Shaped Holes** (Receiving cavities)
- Precision-manufactured holes matching each peg shape
- Available in 3 tolerance levels:
  - **0.1mm** - Extremely tight fit, tests precision
  - **1mm** - Standard assembly tolerance
  - **3mm** - Loose tolerance for ease of insertion
- Each tolerance level contains all 5 shapes

### Tolerance Levels Explained

- **0.1mm**: Requires high precision, minimal play
- **1mm**: Standard engineering tolerance, typical assembly
- **3mm**: Forgiving tolerance, easy insertion but less precision

## Image Assets

### Photos/ Directory
Contains PNG images of each peg shape at different tolerances:
- `Circle_0.1.png`, `Circle_1.png`, `Circle_3.png`
- `Triangle_0.1.png`, `Triangle_1.png`, `Triangle_3.png`
- `Rectangle_0.1.png`, `Rectangle_1.png`, `Rectangle_3.png`
- `Hexagon_0.1.png`, `Hexagon_1.png`, `Hexagon_3.png`
- `L-Shape_0.1.png`, `L-Shape_1.png`, `L-Shape_3.png`
- Base piece images: `base.png`, `corner-base.png`, `line-base.png`, `cross-base.png`

### Photos_45/ Directory
Same images rotated/optimized for 45° diagonal orientations:
- `Circle_0.1_45.png`, `Circle_1_45.png`, `Circle_3_45.png`
- `Triangle_0.1_45.png`, `Triangle_1_45.png`, `Triangle_3_45.png`
- `Rectangle_0.1_45.png`, `Rectangle_1_45.png`, `Rectangle_3_45.png`
- `Hexagon_0.1_45.png`, `Hexagon_1_45.png`, `Hexagon_3_45.png`
- `L-Shape_0.1_45.png`, `L-Shape_1_45.png`, `L-Shape_3_45.png`

## Key Features

- **Reproducible Generation**: Use seeds to recreate exact scenarios
- **Multiple Difficulty Levels**: Varying tolerances and shape complexity
- **Flexible Orientations**: 8 possible angles with diagonal awareness
- **Visual Feedback**: PNG images for all piece types and tolerances
- **Assembly Constraints**: Validates piece connectivity for base configurations
- **Grid-Based Placement**: 3x3 grid for systematic piece placement

## Assembly System

The tool includes logic for validating piece connections:

**Connector Types**:
- `joint` - Protrusion that connects into a hole
- `hole` - Cavity that receives a joint
- `none` - No connector

**Connection Rules**:
- Joints must connect to holes (one-to-one mapping)
- Opposite sides have complementary connectors
- Base pieces have fixed connector patterns

## For Developers

### Main Components

1. **PieceImageStore** - Manages image loading and rotation
2. **Scenario Builder** - Creates task sequences
3. **Layout Planner** - Validates piece connectivity
4. **Seed Management** - Ensures reproducibility

### Adding New Shapes

1. Create STL files in `STL Files/Pegs/[shape]/`
2. Add cavity files in `STL Files/Shaped-holes/[tolerance]/[shape]_[tolerance].stl`
3. Add PNG images to `Photos/` and `Photos_45/`
4. Update `SHAPES` list in `Generate_Scenario.py`
5. Add connector mapping in `PIECE_CONNECTORS_0` if needed

### Adding New Tolerances

1. Create new cavity files: `STL Files/Shaped-holes/[tolerance]/`
2. Add new PNG images to `Photos/` with naming: `[Shape]_[tolerance].png`
3. Update `TOLERANCES` list in the script
4. Update `_normalize_tolerance_token()` function if needed

## Troubleshooting

**Images not found**: Ensure image directory structure matches expected layout
```
Photos/
├── Circle_0.1.png
├── Circle_1.png
├── Triangle_0.1.png
└── ...
```

**No valid layouts found**: Check that base connection mappings are compatible

**Seed not reproducing**: Ensure using same Python version and random seed
