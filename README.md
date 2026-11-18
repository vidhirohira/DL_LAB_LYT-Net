# LYT-Net: Low-Light Image Enhancement Mini-Project
**VJTI | B.Tech Computer Engineering | Deep Learning Lab (Sem VII)**

[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C.svg?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Parameters](https://img.shields.io/badge/Parameters-12.06K-blue.svg)](#architecture)
[![Checkpoint Size](https://img.shields.io/badge/Size-72%20KB-blue.svg)](#architecture)
[![Test PSNR](https://img.shields.io/badge/Test%20PSNR-18.68%20dB-brightgreen.svg)](#quantitative-results)
[![Test SSIM](https://img.shields.io/badge/Test%20SSIM-0.7777-brightgreen.svg)](#quantitative-results)
[![Interactive Demo](https://img.shields.io/badge/Gradio%20Demo-infer.py%20--gradio-orange.svg)](#live-viva-demonstration--single-image-inference)

---

## 📌 Project Overview & Objectives
This project adapts and evaluates **LYT-Net** (Lightweight YUV Transformer-based Network) for practical low-light image enhancement (LLIE). By decoupling luminance ($Y$) from chrominance ($U, V$), the network separately optimizes illumination recovery and color-noise suppression with only **12,060 parameters** (~72 KB checkpoint), making it suitable for edge and mobile deployment.

Key contributions of this implementation:
1. **Unified Dataset Pipeline**: Combined LOL-v1 and LOL-v2 (Real-captured and Synthetic) into a single dataset with **2,074 training pairs** and **215 test pairs** (2,289 total pairs).
2. **Custom 4-Term Hybrid Loss**: Formulated a multi-objective loss combining **Smooth L1**, **SSIM**, **Cosine Color Similarity**, and **Horizontal Gradient Edge Loss**.
3. **100-Epoch Convergence**: Trained from scratch for 100 epochs using AdamW ($3 \times 10^{-4}$) with Cosine Annealing learning rate scheduling.
4. **Live Viva Demonstration Tool (`infer.py`)**: An interactive Gradio web application and CLI inference script with fast latency telemetry (<100 ms).
5. **Comprehensive Metric Analysis & Export**: Evaluated across LOL-v1, LOL-v2 Real, and LOL-v2 Synthetic splits, generating full side-by-side comparison imagery.

---

## 🧠 Architecture Highlights
LYT-Net uses a dual-branch processing pipeline based on YUV color space decomposition:

```
                      ┌──> Y Branch (Luminance) ──> CWD1 ──> MHSA ──> CWD2 ──┐
Input RGB ──> RGB2YUV ┤                                                      ├──> YUV2RGB ──> Fusion ──> Enhanced RGB
                      └──> UV Branch (Chrominance) ─> CWD1 ───────> CWD2 ────┘
```

- **Y-Branch (Luminance)**: Employs a **Channel-Wise Denoiser (CWD)** and a **Lightweight Multi-Head Self-Attention (MHSA)** module to capture long-range contextual illumination dependencies and dynamic range adjustments.
- **UV-Branch (Chrominance)**: Processes chromatic information using dual CWD blocks to suppress high-frequency noise and prevent color casts without expensive self-attention.
- **Multi-Stage Squeeze & Excite Fusion (MSEF)**: Fuses spatial details and chrominance back into RGB with residual refinements.
- **Complexity**: Only **12,060 parameters** (~72 KB file size) and **3.49 GFLOPs**, ~50x to 100x smaller than conventional diffusion or large CNN-based low-light restorers.

---

## 📐 Custom 4-Term Hybrid Loss Function
To address simultaneous underexposure, perceptual degradation, color distortion, and edge blurring, we replaced standard L1 loss with a custom 4-term hybrid objective:

$$\mathcal{L}_{\text{total}} = \lambda_1 \mathcal{L}_{\text{Smooth L1}} + \lambda_2 \mathcal{L}_{\text{SSIM}} + \lambda_3 \mathcal{L}_{\text{color}} + \lambda_4 \mathcal{L}_{\text{grad}}$$

Where:
1. **Smooth L1 Loss ($\lambda_1 = 1.0$)**:
   $$\mathcal{L}_{\text{Smooth L1}}(\hat{I}, I) = \begin{cases} 0.5 (\hat{I} - I)^2 / \beta, & \text{if } |\hat{I} - I| < \beta \\ |\hat{I} - I| - 0.5 \beta, & \text{otherwise} \end{cases}$$
   Provides robust pixel-level intensity alignment without over-penalizing high-contrast outliers.
2. **SSIM Perception Loss ($\lambda_2 = 1.0$)**:
   $$\mathcal{L}_{\text{SSIM}}(\hat{I}, I) = 1 - \text{SSIM}(\hat{I}, I)$$
   Preserves structural similarity, high-frequency details, and localized contrast perception.
3. **Cosine Color Similarity Loss ($\lambda_3 = 0.5$)**:
   $$\mathcal{L}_{\text{color}}(\hat{I}, I) = 1 - \frac{1}{H \cdot W} \sum_{x, y} \frac{\hat{I}(x,y) \cdot I(x,y)}{\|\hat{I}(x,y)\|_2 \|I(x,y)\|_2 + \epsilon}$$
   Constrains the angle between predicted and ground-truth RGB color vectors, preventing chromatic distortion and unnatural hue shifts.
4. **Horizontal Gradient Edge Loss ($\lambda_4 = 0.5$)**:
   $$\mathcal{L}_{\text{grad}}(\hat{I}, I) = \|\nabla_x \hat{I} - \nabla_x I\|_1$$
   Penalizes edge smoothing along image structures to restore crisp boundaries and fine textures.

---

## 📊 Quantitative Results

### 1. Test Dataset Breakdown
Evaluated across all **215 unseen test images** using the converged 100-epoch checkpoint (`lytnet_from_scratch.pth`):

| Dataset Split | Test Images | Standard PSNR (dB) | Standard SSIM | Mean-Matched PSNR (dB)* | Mean-Matched SSIM* |
|:---|:---:|:---:|:---:|:---:|:---:|
| **LOL-v1** | 15 | **19.24 dB** | **0.7781** | 24.09 dB | 0.8014 |
| **LOL-v2 Real** | 100 | **18.99 dB** | **0.8058** | 26.79 dB | 0.8434 |
| **LOL-v2 Synthetic** | 100 | **18.29 dB** | **0.7496** | 25.42 dB | 0.8210 |
| **Overall Combined** | **215** | **18.68 dB** | **0.7777** | **25.96 dB** | **0.8299** |

*\*Note: Mean-matched metrics normalize global illumination scale differences between low-light captures and reference studio ground truths, commonly reported in low-light literature.*

---

### 2. 100-Epoch Training Convergence Curve
Trained using AdamW ($\text{lr}=3\times 10^{-4}$, weight decay $1\times 10^{-4}$) with Cosine Annealing learning rate schedule on the combined 2,074-image training set:

| Epoch | Combined Train Loss | Combined Test PSNR (dB) | Combined Test SSIM | Key Milestones |
|:---:|:---:|:---:|:---:|:---|
| **1** | 0.3591 | 13.89 dB | 0.5882 | Base initialization; preliminary luminance brightening |
| **10** | 0.1673 | 17.12 dB | 0.7312 | Rapid structural alignment and noise suppression |
| **20** | 0.1590 | 17.04 dB | 0.7397 | Steady color balance stabilization |
| **30** | 0.1491 | 17.80 dB | 0.7593 | Gradient edge loss refines object contours |
| **40** | 0.1480 | 18.49 dB | 0.7675 | Major perceptual quality leap across real dark scenes |
| **50** | 0.1409 | 18.50 dB | 0.7743 | SSIM stabilizes above 0.77 |
| **60** | 0.1418 | 18.47 dB | 0.7715 | Learning rate decays via Cosine Annealing |
| **70** | 0.1403 | **18.68 dB** | 0.7765 | **Peak Validation PSNR achieved (18.68 dB)** |
| **80** | 0.1388 | 18.58 dB | 0.7773 | Fine-tuning edge textures and shadow regions |
| **90** | 0.1381 | 18.56 dB | 0.7772 | Loss reaches minimum plateau (0.1381) |
| **100** | **0.1392** | 18.59 dB | **0.7777** | **Final Convergence: Peak SSIM (0.7777)** |

---

## 🚀 Live Viva Demonstration & Single-Image Inference

### 1. Interactive Gradio Web Demo (Recommended for Viva)
Launch a clean web interface in your browser to enhance custom dark photos in real time:
```bash
python infer.py --gradio
```
- Open `http://127.0.0.1:7860` in any browser.
- Drag and drop any dark photo (supports PNG, JPG, JPEG, and iPhone HEIC).
- Displays side-by-side before/after comparison with latency telemetry (<100 ms on GPU/MPS).
- Comes preloaded with clickable LOL test examples.

### 2. Single-Image Command-Line Inference
Enhance an arbitrary image and automatically generate a side-by-side comparison:
```bash
python infer.py --image path/to/dark_image.png --output enhanced.png
```
This produces:
- `enhanced.png`: High-resolution restored image.
- `enhanced_comparison.png`: Formatted `[Low-Light Input | LYT-Net Output]` panel.

---

## 🛠️ Reproduction & Scripts Guide

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/vidhirohira/DL_LAB_LYT-Net.git
cd DL_LAB_LYT-Net

# Install dependencies
pip install torch torchvision numpy pillow matplotlib torchmetrics gradio pillow-heif
```

### 2. Data Preparation
Download and organize LOL-v1 and LOL-v2 automatically:
```bash
python download_data.py
```
Expected directory structure:
```
data/
├── LOLv1/
│   ├── Train/ (input, target) [485 pairs]
│   └── Test/  (input, target) [15 pairs]
└── LOLv2/
    ├── Real_captured/ (Train, Test) [689 train, 100 test]
    └── Synthetic/     (Train, Test) [900 train, 100 test]
```

### 3. Model Training
```bash
python PyTorch/train.py --epochs 100 --batch_size 8 --lr 3e-4 --data_root data
```

### 4. Full Dataset Evaluation & Image Export
Run evaluation and export side-by-side comparison panels for all pairs:
```bash
python PyTorch/evaluate.py --weights lytnet_from_scratch.pth --data_root data
```
Outputs:
- `results/comparisons/`: 5 publication-ready test plots and a composite master grid.
- `results/all_1000_comparisons/`: 2,289 3-panel horizontal comparison images.
- `results/all_1000_pairs/`: Organized into `input/`, `output/`, and `ground_truth/`.

---

## 📁 Repository Structure
```
├── README.md                  # Comprehensive project documentation
├── .gitignore                 # Excludes raw data (data/) and heavy results (results/)
├── infer.py                   # Live viva demo (Gradio UI & CLI inference)
├── download_data.py           # Automated dataset downloader & unpacker
├── lytnet_from_scratch.pth    # Converged 100-epoch weights (72 KB, 12,060 params)
├── best_model.pth             # Standalone checkpoint (195 KB)
├── build_presentation.py      # Automated 16:9 presentation builder (PPTX & PDF)
├── generate_report_pdf.py     # Academic PDF report generator
├── Final_Report_and_PPT/      # Deliverables folder with finalized Report & Presentation
│   ├── Vidhi Rohira LY BTECH CE 52 - DL LAB PROJECT Report.pdf
│   ├── Vidhi Rohira LY BTECH CE 52:- DL LAB PROJECT.pdf
│   └── Vidhi Rohira LY BTECH CE 52:- DL LAB PROJECT.pptx
├── PyTorch/
│   ├── model.py               # LYT and LYTNet (dim=24) with auto-detection loader
│   ├── losses.py              # Custom 4-term hybrid loss implementation
│   ├── dataloader.py          # Multi-dataset loader with synchronized augmentations
│   ├── train.py               # 100-epoch training loop with Cosine Annealing
│   └── evaluate.py            # Evaluation & fast PIL comparison generator
└── results/
    ├── report_figures/        # Architecture diagrams, loss curves, and benchmarks
    └── generate_figures.py    # Figure generation script
```

---

## 📜 References
- **LYT-Net Paper**: Brateanu et al., *"LYT-Net: Lightweight YUV Transformer-based Network for Low-Light Image Enhancement"*, IEEE Signal Processing Letters, 2025.
- **LOL Dataset**: Wei et al., *"Deep Retinex Decomposition for Low-Light Enhancement"*, BMVC 2018.
