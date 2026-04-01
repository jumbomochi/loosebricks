# Lego Brick ML Recognition — Research Report

Date: 2026-04-01

## Summary

Survey of existing ML models, datasets, research, and commercial solutions for identifying Lego bricks from photos. The goal is to inform the ML Recognition Service architecture for LooseBricks.

## 1. Production-Ready Models

### Brickognize

- **Scope**: 80,000+ parts, sets, and minifigures
- **Architecture**: ConvNeXt-T (28M parameters), trained in PyTorch/Lightning
- **Performance**: 91.3% segmentation AP50 on uncontrolled images (using synthetic + 20 real images)
- **Availability**: Free API with Swagger docs at https://api.brickognize.com/docs
- **Paper**: https://www.mdpi.com/1424-8220/23/4/1898
- **Website**: https://brickognize.com/

### RebrickNet (by Rebrickable)

- **Scope**: 200+ parts from photos of multiple pieces on a flat surface
- **Performance**: 93% part accuracy, 80% color accuracy, 77% combined
- **Training data**: 4,700+ user-submitted videos (300,000 images)
- **Website**: https://rebrickable.com/rebricknet/

### HuggingFace Models

- `magichampz/lego-technic-sorting-model` — 7 Technic categories, 93% accuracy, 6,000 training images
- `mw00/yolov7-lego` — YOLOv7 trained on 600-part Kaggle dataset
- `pvrancx/legobricks` — Dataset with 1,000 classes x 400 rendered images (400K total)

### Notable GitHub Projects

- [OpenBlok](https://github.com/blokbot-io/OpenBlok) — Open-source identification and sorting system with multiple AI models
- [LegoSorter](https://github.com/LegoSorter/LegoSorter) — Full pipeline: Blender rendering, model training, backend, Android app
- [LegoBrickClassification](https://github.com/jtheiner/LegoBrickClassification) — ResNeXt50/ResNet34, transfer learning, LDraw renders via Blender

### Roboflow Universe

Multiple pre-trained models and annotated datasets available at https://universe.roboflow.com/search?q=class:lego

## 2. Datasets

| Dataset | Size | Type | Coverage |
|---------|------|------|----------|
| Gdansk University (Nature, 2023) | 155K photos + 1.5M renders | Real + synthetic | Multiple part categories |
| B200C Classification | 800K images (200 parts x 4,000) | Synthetic renders | 200 most popular parts |
| pvrancx/legobricks (HuggingFace) | 400K images (1,000 classes x 400) | Rendered from LDraw | 1,000 part IDs linked to BrickLink/Rebrickable |
| Kaggle Largest (600 parts) | ~150K+ images | Domain-randomized synthetic | 600 parts |
| ICCS 2022 dataset | 52K photos + 567K renders | Mixed | 447 distinct parts |
| Lego Brick Sorting | 4,580 photos | Real photos | 20 parts |

**Key insight**: Nearly all serious projects use **LDraw 3D models rendered via Blender** (with ImportLDraw extension) to generate synthetic training data. Photographing thousands of individual parts is impractical.

**Sources**:
- Gdansk paper: https://www.nature.com/articles/s41597-023-02682-2
- Curated list: https://github.com/360er0/awesome-lego-machine-learning

## 3. Research Papers — Key Findings

### Architecture

A **two-stage pipeline** (detect individual bricks, then classify each) consistently outperforms single-stage approaches:

1. **Detection stage**: Mask R-CNN or YOLO variants to find and segment individual bricks in a pile photo
2. **Classification stage**: ResNet-50 or ConvNeXt to identify each detected brick by part number and color

This is the approach used by both Brickit (commercial) and Brickognize (academic/API).

### Performance Benchmarks

- ResNet-50 achieved 93.81% Top-1 / 99.10% Top-5 on 447-class classification (ICCS 2022)
- ResNet-34 recommended as best balance of depth vs. performance
- End-to-end pipeline (detection + classification) typically ~71% accuracy, with detection at 87% but IoU at 63%
- Color may actually hurt classification — grayscale slightly outperformed RGB in some experiments

### Domain Gap

The gap between synthetic renders and real photos is the core training challenge:
- EfficientNetB0 dropped from ~100% on mixed data to 80% on renders-only
- Photo-realistic rendering (Brickognize approach) significantly closes this gap

### Occlusion

The hardest unsolved problem:
- Models trained on non-occluded data drop from ~91% to ~65% on occluded test sets
- Training specifically on occluded data restores accuracy to ~88%
- All systems recommend spreading pieces apart on a contrasting background

### Key Papers

- "Brickognize: Applying Photo-Realistic Image Synthesis for Lego Bricks Recognition with Limited Data" (Sensors, 2023) — https://www.mdpi.com/1424-8220/23/4/1898
- "How to Sort Them? A Network for LEGO Bricks Classification" (ICCS 2022) — https://link.springer.com/chapter/10.1007/978-3-031-08757-8_52
- "Photos and Rendered Images of LEGO Bricks" (Nature Scientific Data, 2023) — https://www.nature.com/articles/s41597-023-02682-2
- "LEGO Co-builder" (arXiv, July 2025) — https://arxiv.org/abs/2507.05515

## 4. Foundation Models (GPT-4o, Claude, Gemini)

**Not viable as the primary recognizer.**

The "LEGO Co-builder" benchmark (2025) tested GPT-4o, Gemini, and Qwen-VL on Lego assembly tasks:
- GPT-4o max F1: **40.54%** on state detection
- All models struggled with fine-grained spatial reasoning and precise part identification

No published benchmarks exist for using multimodal LLMs specifically for part-number identification. Anecdotally they can identify broad categories ("2x4 brick") but cannot distinguish among thousands of similar parts.

**Potential supplementary role**: Natural-language interaction, ambiguous case fallback, or user-facing explanations — but not as the core recognition engine.

## 5. Commercial Competitors

| Product | Platform | Recognition Scope | Tech | Pricing |
|---------|----------|-------------------|------|---------|
| [Brickit](https://brickit.app/) | iOS + Android | 100 (free) / 1,600 (Pro) parts | Two on-device neural nets, runs offline | Free + Pro subscription |
| [Brickognize](https://brickognize.com/) | Web + API | 80,000+ parts | ConvNeXt-T, cloud-based | Free |
| [Bricksee](https://www.videosdk.live/ai-apps/bricksee) | iOS + Android | 10,000+ sets | Deep learning + CV | Free |
| [Instabrick](https://www.instabrick.org/) | Hardware + cloud | Part identification | USB camera + LED box, DART AI (Getcoo) | Hardware purchase |
| [Bricqer](https://bricqer.com/) | SaaS | Integrated Brickognize | Cloud inventory + camera recognition | Subscription (B2B) |
| [RebrickNet](https://rebrickable.com/rebricknet/) | Web | 200+ parts | User-trained on video submissions | Free |

**Brickit** is the closest competitor to LooseBricks — scans a pile, identifies bricks, suggests builds. Uses two separate on-device neural networks (detection + classification).

## 6. Recommendations for LooseBricks

### MVP Strategy

Use the **Brickognize API** as the ML service. It's free, covers 80K+ parts, has documented API endpoints, and provides confidence scores — exactly what the PRD specifies. This avoids building a model from scratch for launch.

### Custom Model (Parallel Track)

1. **Architecture**: Two-stage pipeline — YOLO (v7+) for detection, ResNet-50 or ConvNeXt-T for classification
2. **Training data**: Start with `pvrancx/legobricks` (1,000 classes) + Gdansk renders, augment with user-confirmed corrections over time
3. **Domain gap mitigation**: Use photo-realistic Blender renders (Brickognize approach) and fine-tune with real photos as they accumulate from user scans
4. **Occlusion handling**: Include occluded training examples from the start; the PRD's guidance overlay ("spread pieces apart") also helps

### Key Resource

[awesome-lego-machine-learning](https://github.com/360er0/awesome-lego-machine-learning) — the most comprehensive index of all Lego ML papers, datasets, models, and tools.
