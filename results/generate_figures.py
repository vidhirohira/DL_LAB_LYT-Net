#!/usr/bin/env python3
"""
Generate all 300 DPI figures for the academic VJTI report:
- fig1_pipeline_flowchart.png
- fig2_architecture_diagram.png
- fig3_loss_architecture.png
- fig4_training_curves.png
- fig5_subset_benchmarks.png
- visual_sample_1.png to visual_sample_5.png
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
import torch
import torchvision.transforms.functional as TF

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'PyTorch'))

from model import load_model
from train import calculate_psnr, calculate_ssim

OUTPUT_DIR = os.path.join(PROJECT_DIR, "results", "report_figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Set high-quality styling
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.edgecolor'] = '#cbd5e1'
plt.rcParams['axes.linewidth'] = 1.0


# ==============================================================================
# Figure 1: End-to-End System Pipeline Flowchart
# ==============================================================================
def generate_fig1_pipeline():
    fig, ax = plt.subplots(figsize=(14, 6.5), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 6.5)
    ax.axis('off')
    fig.patch.set_facecolor('#ffffff')

    def draw_box(x, y, w, h, title, subtitle, fill_color, border_color, title_color='#0f172a', sub_color='#334155'):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1,rounding_size=0.15",
                                      facecolor=fill_color, edgecolor=border_color, linewidth=1.5, zorder=2)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h*0.64, title, ha='center', va='center', fontsize=11, fontweight='bold', color=title_color, zorder=3)
        ax.text(x + w/2, y + h*0.32, subtitle, ha='center', va='center', fontsize=8.5, color=sub_color, zorder=3)

    def draw_arrow(x1, y1, x2, y2, label=""):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#3b82f6", lw=2.2, mutation_scale=15), zorder=4)
        if label:
            ax.text((x1 + x2)/2, (y1 + y2)/2 + 0.18, label, ha='center', va='center', fontsize=8.5, fontweight='bold', color='#1d4ed8', zorder=5)

    # 1. Input Datasets
    draw_box(0.5, 4.3, 2.5, 1.4, "Multi-Domain Data", "LOL-v1 + LOL-v2 (R & S)\n2,289 Image Pairs", "#eff6ff", "#93c5fd")
    
    # 2. Preprocessing & Augmentation
    draw_box(3.6, 4.3, 2.6, 1.4, "Data Augmentation", "256x256 Random Crops\nReflection Pad + Flip", "#f0fdf4", "#86efac")
    
    # 3. YUV Color Decoupling
    draw_box(6.8, 4.3, 2.7, 1.4, "YUV Decoupling", "RGB -> Y (Luminance)\nRGB -> UV (Chrominance)", "#fef3c7", "#fde047")

    # 4. Dual-Branch Network
    draw_box(10.1, 4.3, 3.2, 1.4, "LYT-Net Architecture", "Y: CWD + Pooled MHSA\nUV: Dual CWD Blocks\n~12K Params (dim=24)", "#f5f3ff", "#c4b5fd")

    # Lower branch: Training & Loss vs Deployment
    draw_box(10.1, 1.2, 3.2, 1.6, "MSEF Recombination", "Inverse YUV -> RGB\n+ Residual Fusion\nEnhanced RGB Image", "#fdf2f8", "#f472b6")

    draw_box(5.5, 1.2, 3.8, 1.6, "4-Term Hybrid Loss", "Smooth L1 (1.0) + SSIM (0.5)\n+ Cosine Color (0.1) + Edge (0.1)\nAdamW + Cosine Anneal", "#fff7ed", "#fdba74")

    draw_box(0.5, 1.2, 4.2, 1.6, "Evaluation & Live Viva Demo", "Modular CLI & Gradio UI\nAll 2,289 Pair Comparisons\nSub-100ms Inference Telemetry", "#ecfeff", "#67e8f9")

    # Arrows
    draw_arrow(3.0, 5.0, 3.6, 5.0)
    draw_arrow(6.2, 5.0, 6.8, 5.0)
    draw_arrow(9.5, 5.0, 10.1, 5.0)
    
    # Down arrow from network to fusion
    ax.annotate('', xy=(11.7, 2.8), xytext=(11.7, 4.3),
                arrowprops=dict(arrowstyle="->", color="#3b82f6", lw=2.2, mutation_scale=15), zorder=4)
    ax.text(11.75, 3.55, "Y, UV Enh", ha='left', va='center', fontsize=8.5, fontweight='bold', color='#1d4ed8')

    # Arrow from fusion to loss
    draw_arrow(10.1, 2.0, 9.3, 2.0, "Backward Gradient")

    # Arrow from loss to demo
    draw_arrow(5.5, 2.0, 4.7, 2.0, "Trained Weights")

    plt.tight_layout()
    fig_path = os.path.join(OUTPUT_DIR, "fig1_pipeline_flowchart.png")
    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {fig_path}")


# ==============================================================================
# Figure 2: Detailed LYT-Net CNN-Transformer Architecture & Layer Diagram
# ==============================================================================
def generate_fig2_architecture():
    fig, ax = plt.subplots(figsize=(15, 8.5), dpi=300)
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.5)
    ax.axis('off')
    fig.patch.set_facecolor('#ffffff')

    def draw_card(x, y, w, h, title, details, header_bg, body_bg, border_color):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                                      facecolor=body_bg, edgecolor=border_color, linewidth=1.5, zorder=2)
        ax.add_patch(rect)
        hdr = patches.FancyBboxPatch((x, y + h - 0.55), w, 0.55, boxstyle="round,pad=0.08,rounding_size=0.12",
                                     facecolor=header_bg, edgecolor=border_color, linewidth=1.5, zorder=3)
        ax.add_patch(hdr)
        ax.text(x + w/2, y + h - 0.28, title, ha='center', va='center', fontsize=9.5, fontweight='bold', color='#ffffff', zorder=4)
        ax.text(x + 0.15, y + (h - 0.55)/2, details, ha='left', va='center', fontsize=8.0, color='#1e293b', zorder=4, linespacing=1.35)

    def draw_arrow(x1, y1, x2, y2, color="#2563eb", label=""):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2.0, mutation_scale=14), zorder=5)
        if label:
            ax.text((x1+x2)/2, (y1+y2)/2 + 0.15, label, ha='center', va='center', fontsize=7.5, fontweight='bold', color=color, zorder=6)

    # Input Box
    draw_card(0.4, 3.8, 1.8, 2.0, "Input Image", "Low-Light RGB\nShape: (B, 3, H, W)\nNormalized: [0, 1]", "#1e293b", "#f8fafc", "#64748b")

    # RGB to YUV Decoupler
    draw_card(2.6, 3.5, 2.2, 2.6, "YUV Decoupling", "RGB -> YUV Split:\nY = 0.299R+0.587G+0.114B\nU = -0.147R-0.289G+0.436B\nV = 0.615R-0.515G-0.100B", "#0284c7", "#f0f9ff", "#38bdf8")

    # Top Branch: Luminance Y
    draw_card(5.3, 5.2, 2.3, 2.6, "Y-Branch (Luminance)", "Conv2d(1 -> 24)\nShape: (B, 24, H, W)\nCWDBlock 1 (SE + DW)\nIllumination Recovery", "#d97706", "#fffbeb", "#f59e0b")
    draw_card(8.0, 5.2, 2.6, 2.6, "Lightweight MHSA", "AdaptiveAvgPool(16x16)\nMultiheadAttn(h=4, d=24)\nBilinear Upsample (H, W)\nGlobal Context (Tokens: 256)", "#7c3aed", "#faf5ff", "#a855f7")
    draw_card(11.0, 5.2, 2.2, 2.6, "Y Output Refine", "CWDBlock 2\nConv2d(24 -> 1)\nResidual Add:\nY_enh = Y + Y_res", "#b45309", "#fffbeb", "#f59e0b")

    # Bottom Branch: Chrominance UV
    draw_card(5.3, 1.0, 2.3, 2.6, "UV-Branch (Color)", "Conv2d(2 -> 24)\nShape: (B, 24, H, W)\nCWDBlock 1\nNoise Suppression", "#059669", "#ecfdf5", "#34d399")
    draw_card(8.0, 1.0, 2.6, 2.6, "UV Denoising (CWD 2)", "CWDBlock 2 (dim=24)\nPreserves Color Hue\nZero Heavy Self-Attention\nUltra-Fast Computation", "#047857", "#ecfdf5", "#34d399")
    draw_card(11.0, 1.0, 2.2, 2.6, "UV Output Refine", "Conv2d(24 -> 2)\nResidual Add:\nUV_enh = UV + UV_res\nShape: (B, 2, H, W)", "#065f46", "#ecfdf5", "#34d399")

    # Recombination & Fusion
    draw_card(12.3, 3.4, 2.3, 2.6, "Fusion & Output", "Inverse YUV -> RGB\n+ Conv(3->24) + GELU\n+ MSEFBlock(dim=24)\n+ Conv(24->3)\nOut: (B, 3, H, W)", "#be185d", "#fdf2f8", "#f472b6")

    # Connecting arrows
    draw_arrow(2.2, 4.8, 2.6, 4.8)
    draw_arrow(4.8, 5.5, 5.3, 6.2, label="Y: (B, 1, H, W)")
    draw_arrow(4.8, 4.1, 5.3, 2.5, label="UV: (B, 2, H, W)")
    
    # Y-branch arrows
    draw_arrow(7.6, 6.5, 8.0, 6.5)
    draw_arrow(10.6, 6.5, 11.0, 6.5)

    # UV-branch arrows
    draw_arrow(7.6, 2.3, 8.0, 2.3)
    draw_arrow(10.6, 2.3, 11.0, 2.3)

    # Convergence into fusion
    draw_arrow(12.1, 5.2, 12.8, 4.8, label="Y_enh")
    draw_arrow(12.1, 2.5, 12.8, 4.0, label="UV_enh")

    plt.tight_layout()
    fig_path = os.path.join(OUTPUT_DIR, "fig2_architecture_diagram.png")
    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {fig_path}")


# ==============================================================================
# Figure 3: 4-Component Hybrid Loss Architecture Diagram
# ==============================================================================
def generate_fig3_loss():
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=300)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.5)
    ax.axis('off')
    fig.patch.set_facecolor('#ffffff')

    def draw_term_card(x, y, w, h, title, formula, role, weight, color_hdr, color_bg, border):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.1",
                                      facecolor=color_bg, edgecolor=border, linewidth=1.5, zorder=2)
        ax.add_patch(rect)
        hdr = patches.FancyBboxPatch((x, y + h - 0.5), w, 0.5, boxstyle="round,pad=0.08,rounding_size=0.1",
                                     facecolor=color_hdr, edgecolor=border, linewidth=1.5, zorder=3)
        ax.add_patch(hdr)
        ax.text(x + w/2, y + h - 0.25, f"{title} (w = {weight})", ha='center', va='center', fontsize=9.5, fontweight='bold', color='#ffffff', zorder=4)
        ax.text(x + 0.15, y + h - 0.85, f"Formula: {formula}", ha='left', va='center', fontsize=8.2, fontweight='bold', color='#0f172a', zorder=4)
        ax.text(x + 0.15, y + 0.45, f"Function: {role}", ha='left', va='center', fontsize=7.8, color='#334155', zorder=4)

    # Inputs: Pred and Target
    rect_pred = patches.FancyBboxPatch((0.5, 4.0), 2.2, 1.4, boxstyle="round,pad=0.08", facecolor="#eff6ff", edgecolor="#3b82f6", lw=1.5)
    ax.add_patch(rect_pred)
    ax.text(1.6, 4.9, "Model Output (Î)", ha='center', va='center', fontsize=10, fontweight='bold', color='#1e3a8a')
    ax.text(1.6, 4.4, "Enhanced Image\nShape: (B, 3, H, W)", ha='center', va='center', fontsize=8, color='#475569')

    rect_gt = patches.FancyBboxPatch((0.5, 1.4), 2.2, 1.4, boxstyle="round,pad=0.08", facecolor="#f0fdf4", edgecolor="#22c55e", lw=1.5)
    ax.add_patch(rect_gt)
    ax.text(1.6, 2.3, "Ground Truth (I)", ha='center', va='center', fontsize=10, fontweight='bold', color='#14532d')
    ax.text(1.6, 1.8, "Normal-Light Target\nShape: (B, 3, H, W)", ha='center', va='center', fontsize=8, color='#475569')

    # 4 Loss Term Cards
    draw_term_card(3.8, 4.9, 4.8, 1.35, "1. Smooth L1 Loss", "Smooth_L1(Î, I, beta=1.0)", "Robust pixel-level intensity restoration", "1.0", "#2563eb", "#eff6ff", "#93c5fd")
    draw_term_card(3.8, 3.4, 4.8, 1.35, "2. SSIM Perception Loss", "1.0 - SSIM(Î, I)", "Structural contrast & luminance perception", "0.5", "#7c3aed", "#faf5ff", "#c4b5fd")
    draw_term_card(3.8, 1.9, 4.8, 1.35, "3. Cosine Color Loss", "1.0 - CosSim(Î, I, dim=1)", "Prevents color casts & hue shifts", "0.1", "#059669", "#ecfdf5", "#a7f3d0")
    draw_term_card(3.8, 0.4, 4.8, 1.35, "4. Horiz. Edge Loss", "L1(|∇x Î| , |∇x I|)", "Sharp horizontal edges & crisp details", "0.1", "#d97706", "#fffbeb", "#fde68a")

    # Aggregator Box
    rect_agg = patches.FancyBboxPatch((9.6, 2.2), 2.9, 2.4, boxstyle="round,pad=0.1", facecolor="#f8fafc", edgecolor="#475569", lw=2)
    ax.add_patch(rect_agg)
    ax.text(11.05, 4.0, "Total Hybrid Loss", ha='center', va='center', fontsize=11, fontweight='bold', color='#0f172a')
    ax.text(11.05, 3.1, "L_total = 1.0·L_L1\n+ 0.5·L_SSIM\n+ 0.1·L_color\n+ 0.1·L_edge", ha='center', va='center', fontsize=9, color='#1e293b', linespacing=1.3)
    ax.text(11.05, 2.5, "Replaces Heavy VGG Perceptual Loss", ha='center', va='center', fontsize=7.2, fontstyle='italic', color='#64748b')

    # Connecting arrows
    for y_pos in [5.55, 4.05, 2.55, 1.05]:
        ax.annotate('', xy=(3.8, y_pos), xytext=(2.7, 4.7), arrowprops=dict(arrowstyle="->", color="#3b82f6", lw=1.5))
        ax.annotate('', xy=(3.8, y_pos), xytext=(2.7, 2.1), arrowprops=dict(arrowstyle="->", color="#22c55e", lw=1.5))
        ax.annotate('', xy=(9.6, 3.4), xytext=(8.6, y_pos), arrowprops=dict(arrowstyle="->", color="#475569", lw=1.5))

    plt.tight_layout()
    fig_path = os.path.join(OUTPUT_DIR, "fig3_loss_architecture.png")
    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {fig_path}")


# ==============================================================================
# Figure 4: 100-Epoch Training Curves
# ==============================================================================
def generate_fig4_training_curves():
    epochs = [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    losses = [0.3591, 0.1673, 0.1590, 0.1491, 0.1480, 0.1409, 0.1418, 0.1403, 0.1388, 0.1381, 0.1392]
    psnrs =  [13.89, 17.12, 17.04, 17.80, 18.49, 18.50, 18.47, 18.68, 18.58, 18.56, 18.59]
    ssims =  [0.5882, 0.7312, 0.7397, 0.7593, 0.7675, 0.7743, 0.7715, 0.7765, 0.7773, 0.7772, 0.7777]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), dpi=300)

    # Subplot 1: Hybrid Training Loss
    axes[0].plot(epochs, losses, marker='o', color='#ef4444', linewidth=2.2, markersize=6, label='Hybrid Loss')
    axes[0].set_title("Training Loss Convergence", fontsize=11, fontweight='bold', pad=10)
    axes[0].set_xlabel("Epochs", fontsize=9.5)
    axes[0].set_ylabel("Hybrid Loss Value", fontsize=9.5)
    axes[0].grid(True, linestyle='--', alpha=0.5)
    axes[0].annotate('Rapid Drop\n0.359 -> 0.167', xy=(10, 0.1673), xytext=(22, 0.25),
                     arrowprops=dict(arrowstyle="->", color="#b91c1c", lw=1.2), fontsize=8.5, color="#b91c1c")

    # Subplot 2: Combined Test PSNR
    axes[1].plot(epochs, psnrs, marker='s', color='#2563eb', linewidth=2.2, markersize=6, label='Test PSNR (dB)')
    axes[1].set_title("Validation PSNR (dB)", fontsize=11, fontweight='bold', pad=10)
    axes[1].set_xlabel("Epochs", fontsize=9.5)
    axes[1].set_ylabel("PSNR (dB)", fontsize=9.5)
    axes[1].grid(True, linestyle='--', alpha=0.5)
    axes[1].annotate('Peak PSNR: 18.68 dB\n(Epoch 70)', xy=(70, 18.68), xytext=(45, 17.2),
                     arrowprops=dict(arrowstyle="->", color="#1d4ed8", lw=1.2), fontsize=8.5, fontweight='bold', color="#1d4ed8")

    # Subplot 3: Combined Test SSIM
    axes[2].plot(epochs, ssims, marker='^', color='#059669', linewidth=2.2, markersize=6, label='Test SSIM')
    axes[2].set_title("Validation SSIM", fontsize=11, fontweight='bold', pad=10)
    axes[2].set_xlabel("Epochs", fontsize=9.5)
    axes[2].set_ylabel("SSIM", fontsize=9.5)
    axes[2].grid(True, linestyle='--', alpha=0.5)
    axes[2].annotate('Peak SSIM: 0.7777\n(Epoch 100)', xy=(100, 0.7777), xytext=(65, 0.67),
                     arrowprops=dict(arrowstyle="->", color="#047857", lw=1.2), fontsize=8.5, fontweight='bold', color="#047857")

    plt.tight_layout()
    fig_path = os.path.join(OUTPUT_DIR, "fig4_training_curves.png")
    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {fig_path}")


# ==============================================================================
# Figure 5: Subset-Wise Benchmark Breakdown Chart
# ==============================================================================
def generate_fig5_subset_benchmarks():
    categories = ['LOL-v1\n(15 pairs)', 'LOL-v2 Real\n(100 pairs)', 'LOL-v2 Syn.\n(100 pairs)', 'Combined\n(215 pairs)']
    std_psnr = [19.24, 18.99, 18.29, 18.68]
    mm_psnr =  [24.09, 26.79, 25.42, 25.96]
    
    std_ssim = [0.7781, 0.8058, 0.7496, 0.7777]
    mm_ssim =  [0.8014, 0.8434, 0.8210, 0.8299]

    x = np.arange(len(categories))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.8), dpi=300)

    # PSNR Plot
    rects1 = ax1.bar(x - width/2, std_psnr, width, label='Standard PSNR (dB)', color='#60a5fa', edgecolor='#2563eb')
    rects2 = ax1.bar(x + width/2, mm_psnr, width, label='Mean-Matched PSNR (dB)', color='#3b82f6', edgecolor='#1d4ed8')
    ax1.set_ylabel('PSNR (dB)', fontsize=10)
    ax1.set_title('PSNR Comparison across Test Subsets', fontsize=11, fontweight='bold', pad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, fontsize=9)
    ax1.set_ylim(0, 31)
    ax1.legend(loc='upper right', fontsize=8.5)
    ax1.grid(axis='y', linestyle='--', alpha=0.5)

    for r in rects1:
        h = r.get_height()
        ax1.annotate(f'{h:.2f}', xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3),
                     textcoords="offset points", ha='center', va='bottom', fontsize=8)
    for r in rects2:
        h = r.get_height()
        ax1.annotate(f'{h:.2f}', xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3),
                     textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    # SSIM Plot
    rects3 = ax2.bar(x - width/2, std_ssim, width, label='Standard SSIM', color='#34d399', edgecolor='#059669')
    rects4 = ax2.bar(x + width/2, mm_ssim, width, label='Mean-Matched SSIM', color='#10b981', edgecolor='#047857')
    ax2.set_ylabel('SSIM', fontsize=10)
    ax2.set_title('SSIM Comparison across Test Subsets', fontsize=11, fontweight='bold', pad=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(categories, fontsize=9)
    ax2.set_ylim(0, 1.0)
    ax2.legend(loc='upper right', fontsize=8.5)
    ax2.grid(axis='y', linestyle='--', alpha=0.5)

    for r in rects3:
        h = r.get_height()
        ax2.annotate(f'{h:.4f}', xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3),
                     textcoords="offset points", ha='center', va='bottom', fontsize=8)
    for r in rects4:
        h = r.get_height()
        ax2.annotate(f'{h:.4f}', xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3),
                     textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

    plt.tight_layout()
    fig_path = os.path.join(OUTPUT_DIR, "fig5_subset_benchmarks.png")
    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Generated: {fig_path}")


# ==============================================================================
# Generate 5 Diverse Visual Comparison Images
# ==============================================================================
def generate_visual_comparisons():
    device = torch.device('mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu'))
    model = load_model(os.path.join(PROJECT_DIR, 'lytnet_from_scratch.pth'), device=device)
    model.eval()

    sample_pairs = [
        # 1. LOL-v1 Sample 1
        ("LOL-v1 Indoor Scene (Sample 1)", 
         os.path.join(PROJECT_DIR, "data/LOLv1/Test/input/1.png"), 
         os.path.join(PROJECT_DIR, "data/LOLv1/Test/target/1.png")),
        # 2. LOL-v1 Sample 22
        ("LOL-v1 Shelf & Decor (Sample 22)", 
         os.path.join(PROJECT_DIR, "data/LOLv1/Test/input/22.png"), 
         os.path.join(PROJECT_DIR, "data/LOLv1/Test/target/22.png")),
        # 3. LOL-v2 Real Sample 690
        ("LOL-v2 Real Low-Light Corridor (00690)", 
         os.path.join(PROJECT_DIR, "data/downloads/extracted_v2/LOLv2/Real_captured/Test/Low/00690.png"), 
         os.path.join(PROJECT_DIR, "data/downloads/extracted_v2/LOLv2/Real_captured/Test/Normal/00690.png")),
        # 4. LOL-v2 Real Sample 693
        ("LOL-v2 Real Classroom / Interior (00693)", 
         os.path.join(PROJECT_DIR, "data/downloads/extracted_v2/LOLv2/Real_captured/Test/Low/00693.png"), 
         os.path.join(PROJECT_DIR, "data/downloads/extracted_v2/LOLv2/Real_captured/Test/Normal/00693.png")),
        # 5. LOL-v2 Synthetic Sample
        ("LOL-v2 Synthetic Dynamic Range (r00816405t)", 
         os.path.join(PROJECT_DIR, "data/downloads/extracted_v2/LOLv2/Synthetic/Test/Low/r00816405t.png"), 
         os.path.join(PROJECT_DIR, "data/downloads/extracted_v2/LOLv2/Synthetic/Test/Normal/r00816405t.png"))
    ]

    metrics_records = []

    for idx, (title_desc, low_path, high_path) in enumerate(sample_pairs, start=1):
        low_pil = Image.open(low_path).convert('RGB')
        high_pil = Image.open(high_path).convert('RGB')

        w, h = low_pil.size
        # Resize high if slightly mismatched
        if high_pil.size != (w, h):
            high_pil = high_pil.resize((w, h), Image.Resampling.BILINEAR)

        low_tensor = TF.to_tensor(low_pil).unsqueeze(0).to(device)
        high_tensor = TF.to_tensor(high_pil).unsqueeze(0).to(device)

        # Pad to multiple of 8
        pad_h = (8 - h % 8) % 8
        pad_w = (8 - w % 8) % 8
        if pad_h > 0 or pad_w > 0:
            padded = torch.nn.functional.pad(low_tensor, (0, pad_w, 0, pad_h), mode='reflect')
        else:
            padded = low_tensor

        with torch.no_grad():
            out = model(padded)
            out = torch.clamp(out, 0.0, 1.0)
            if pad_h > 0 or pad_w > 0:
                out = out[:, :, :h, :w]

        psnr_std = calculate_psnr(out, high_tensor, gt_mean=False)
        ssim_std = calculate_ssim(out, high_tensor, gt_mean=False)
        psnr_mm = calculate_psnr(out, high_tensor, gt_mean=True)
        ssim_mm = calculate_ssim(out, high_tensor, gt_mean=True)

        out_np = (out.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)
        out_pil = Image.fromarray(out_np)

        # Plot 3-panel figure using Matplotlib with publication-ready styling
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), dpi=300)
        
        axes[0].imshow(low_pil)
        axes[0].set_title("Low-Light Input", fontsize=11, fontweight='bold', pad=8, color='#1e293b')
        axes[0].axis('off')

        axes[1].imshow(out_pil)
        axes[1].set_title(f"Our LYT-Net Output\n(PSNR: {psnr_std:.2f} dB | SSIM: {ssim_std:.4f})", 
                          fontsize=11, fontweight='bold', pad=8, color='#1d4ed8')
        axes[1].axis('off')

        axes[2].imshow(high_pil)
        axes[2].set_title("Ground Truth (Normal Light)", fontsize=11, fontweight='bold', pad=8, color='#15803d')
        axes[2].axis('off')

        plt.suptitle(f"{title_desc} — Evaluation (Mean-Matched PSNR: {psnr_mm:.2f} dB, SSIM: {ssim_mm:.4f})",
                     fontsize=12, fontweight='bold', y=0.98, color='#0f172a')
        plt.tight_layout()

        out_fig_path = os.path.join(OUTPUT_DIR, f"visual_sample_{idx}.png")
        plt.savefig(out_fig_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Generated Visual Sample {idx}: {out_fig_path}")

        metrics_records.append({
            'idx': idx,
            'title': title_desc,
            'psnr_std': psnr_std,
            'ssim_std': ssim_std,
            'psnr_mm': psnr_mm,
            'ssim_mm': ssim_mm,
            'path': out_fig_path
        })

    return metrics_records


if __name__ == '__main__':
    print("Generating report figures...")
    generate_fig1_pipeline()
    generate_fig2_architecture()
    generate_fig3_loss()
    generate_fig4_training_curves()
    generate_fig5_subset_benchmarks()
    records = generate_visual_comparisons()
    print("All figures successfully created in results/report_figures/!")
