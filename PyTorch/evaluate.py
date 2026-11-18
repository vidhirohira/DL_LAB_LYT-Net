import os
import sys
import argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF

# Ensure local modules are importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from model import LYT, LYTNet, load_model
from dataloader import CombinedLOLDataset, discover_lol_datasets
from train import calculate_psnr, calculate_ssim


# ==============================================================================
# Fast PIL 3-Panel Stitching Utility
# ==============================================================================

def get_font(font_size=18):
    """Loads a clean TrueType font or falls back to PIL default font."""
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for p in font_candidates:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, font_size)
            except Exception:
                pass
    return ImageFont.load_default()


def create_3panel_comparison_image(input_pil, output_pil, gt_pil, font=None, header_h=42, margin=10):
    """
    Fast PIL stitcher creating a clean 3-panel horizontal comparison image:
      [ Low-Light Input | Our LYT-Net Output | Ground Truth ]
    """
    if font is None:
        font = get_font(18)

    w, h = input_pil.size
    # Ensure all 3 images match dimensions
    if output_pil.size != (w, h):
        output_pil = output_pil.resize((w, h), Image.Resampling.BILINEAR)
    if gt_pil.size != (w, h):
        gt_pil = gt_pil.resize((w, h), Image.Resampling.BILINEAR)

    total_w = w * 3 + margin * 4
    total_h = h + header_h + margin * 2

    # Clean off-white background canvas
    canvas = Image.new('RGB', (total_w, total_h), color=(248, 249, 250))
    draw = ImageDraw.Draw(canvas)

    panels = [
        ("Low-Light Input", input_pil, margin),
        ("Our LYT-Net Output", output_pil, margin * 2 + w),
        ("Ground Truth", gt_pil, margin * 3 + w * 2)
    ]

    for title, img, x_offset in panels:
        # Header banner rectangle
        banner_rect = [x_offset, margin, x_offset + w, margin + header_h - 4]
        draw.rectangle(banner_rect, fill=(235, 238, 242))

        # Title text centered within banner
        bbox = draw.textbbox((0, 0), title, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x_offset + (w - tw) // 2
        ty = margin + (header_h - 4 - th) // 2
        draw.text((tx, ty), title, fill=(25, 30, 36), font=font)

        # Paste image below header
        canvas.paste(img, (x_offset, margin + header_h))

    return canvas


# ==============================================================================
# Matplotlib 5-Image Detailed Comparison Plotting
# ==============================================================================

def tensor_to_numpy_image(tensor):
    if tensor.dim() == 4:
        tensor = tensor.squeeze(0)
    tensor = torch.clamp(tensor, 0.0, 1.0)
    np_img = tensor.detach().cpu().permute(1, 2, 0).numpy()
    return np_img


def save_side_by_side_plot(input_img, enhanced_img, gt_img, psnr_val, ssim_val, save_path, sample_idx=1):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), dpi=300)

    axes[0].imshow(input_img)
    axes[0].set_title("Low-Light Input", fontsize=13, fontweight='bold', pad=10)
    axes[0].axis('off')

    axes[1].imshow(enhanced_img)
    axes[1].set_title(f"Our LYT-Net Output\nPSNR: {psnr_val:.2f} dB | SSIM: {ssim_val:.4f}",
                      fontsize=13, fontweight='bold', pad=10, color='darkgreen')
    axes[1].axis('off')

    axes[2].imshow(gt_img)
    axes[2].set_title("Ground Truth", fontsize=13, fontweight='bold', pad=10)
    axes[2].axis('off')

    plt.suptitle(f"Sample #{sample_idx} - Low-Light Enhancement Comparison",
                 fontsize=15, fontweight='bold', y=0.98)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches='tight', dpi=300)
    plt.close(fig)


def save_all_comparisons_grid(samples_data, save_path):
    num_samples = len(samples_data)
    fig, axes = plt.subplots(num_samples, 3, figsize=(15, 4.0 * num_samples), dpi=300)
    if num_samples == 1:
        axes = np.expand_dims(axes, 0)

    col_titles = ["Low-Light Input", "Our LYT-Net Output", "Ground Truth"]

    for row_idx, data in enumerate(samples_data):
        inp = data['input']
        enh = data['enhanced']
        gt = data['gt']
        psnr = data['psnr']
        ssim = data['ssim']
        idx = data['idx']

        axes[row_idx, 0].imshow(inp)
        axes[row_idx, 0].axis('off')
        if row_idx == 0:
            axes[row_idx, 0].set_title(col_titles[0], fontsize=13, fontweight='bold', pad=8)
        axes[row_idx, 0].text(0.02, 0.95, f"#{idx}", transform=axes[row_idx, 0].transAxes,
                              color='white', fontsize=11, fontweight='bold',
                              bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.6))

        axes[row_idx, 1].imshow(enh)
        axes[row_idx, 1].axis('off')
        if row_idx == 0:
            axes[row_idx, 1].set_title(col_titles[1], fontsize=13, fontweight='bold', pad=8)
        axes[row_idx, 1].text(0.02, 0.05, f"PSNR: {psnr:.2f} dB | SSIM: {ssim:.4f}",
                              transform=axes[row_idx, 1].transAxes,
                              color='white', fontsize=10, fontweight='bold',
                              bbox=dict(boxstyle='round,pad=0.2', facecolor='darkgreen', alpha=0.75))

        axes[row_idx, 2].imshow(gt)
        axes[row_idx, 2].axis('off')
        if row_idx == 0:
            axes[row_idx, 2].set_title(col_titles[2], fontsize=13, fontweight='bold', pad=8)

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches='tight', dpi=300)
    plt.close(fig)


# ==============================================================================
# Full Dataset Inference & 3-Panel Stitched Export (~1,000+ images)
# ==============================================================================

def export_all_comparisons_and_pairs(model, data_root, comparisons_dir, pairs_dir, device, gt_mean=True):
    """
    Runs model inference across ALL images in the dataset (both Train and Test splits,
    2,000+ images total) and generates:
      1. results/all_1000_comparisons/XXXX.png (3-panel stitched: Input | LYT-Net Output | GT)
      2. results/all_1000_pairs/input/XXXX.png
      3. results/all_1000_pairs/output/XXXX.png
      4. results/all_1000_pairs/ground_truth/XXXX.png
    """
    print(f"\n==================================================")
    print(f"  Generating 3-Panel Comparisons & Exporting Pairs")
    print(f"==================================================")
    print(f"3-Panel Comparisons Dir : {os.path.abspath(comparisons_dir)}")
    print(f"Individual Pairs Dir    : {os.path.abspath(pairs_dir)}")

    all_pairs_dict, stats = discover_lol_datasets(data_root)
    all_pairs = all_pairs_dict.get('train', []) + all_pairs_dict.get('test', [])
    total_images = len(all_pairs)

    print(f"Total dataset pairs discovered: {total_images}")
    if total_images == 0:
        print(f"[ERROR] No image pairs found under '{data_root}'.")
        return

    os.makedirs(comparisons_dir, exist_ok=True)
    input_dir = os.path.join(pairs_dir, 'input')
    output_dir = os.path.join(pairs_dir, 'output')
    gt_dir = os.path.join(pairs_dir, 'ground_truth')
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(gt_dir, exist_ok=True)

    font = get_font(18)
    total_psnr = 0.0
    total_ssim = 0.0

    model.eval()
    with torch.no_grad():
        for i, (low_path, high_path) in enumerate(all_pairs):
            filename = f"{i + 1:04d}.png"
            comp_file = os.path.join(comparisons_dir, filename)
            inp_file = os.path.join(input_dir, filename)
            out_file = os.path.join(output_dir, filename)
            gt_file = os.path.join(gt_dir, filename)

            # Fast resume: check if all 4 files are already generated
            if (os.path.isfile(comp_file) and os.path.getsize(comp_file) > 1000 and
                os.path.isfile(inp_file) and os.path.isfile(out_file) and os.path.isfile(gt_file)):
                if (i + 1) % 100 == 0 or (i + 1) == total_images:
                    print(f"  [{i + 1:4d}/{total_images:4d}] '{filename}' already exists (resumed).", flush=True)
                continue

            low_pil = Image.open(low_path).convert('RGB')
            high_pil = Image.open(high_path).convert('RGB')

            # Save individual input and ground truth
            low_pil.save(inp_file)
            high_pil.save(gt_file)

            # Tensor conversion and padding to multiple of 8
            low_tensor = TF.to_tensor(low_pil)
            c, h, w = low_tensor.shape
            pad_h = (8 - h % 8) % 8
            pad_w = (8 - w % 8) % 8
            if pad_h > 0 or pad_w > 0:
                padded_input = F.pad(low_tensor.unsqueeze(0), (0, pad_w, 0, pad_h), mode='reflect')
            else:
                padded_input = low_tensor.unsqueeze(0)

            padded_input = padded_input.to(device)
            enhanced = model(padded_input)
            enhanced = torch.clamp(enhanced, 0.0, 1.0)

            if pad_h > 0 or pad_w > 0:
                enhanced = enhanced[:, :, :h, :w]

            enhanced_np = (enhanced.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)
            output_pil = Image.fromarray(enhanced_np)

            # Save individual output
            output_pil.save(out_file)

            # Compute PSNR & SSIM metrics
            high_tensor_batch = TF.to_tensor(high_pil).unsqueeze(0).to(device)
            sample_psnr = calculate_psnr(enhanced, high_tensor_batch, gt_mean=gt_mean)
            sample_ssim = calculate_ssim(enhanced, high_tensor_batch, gt_mean=gt_mean)
            total_psnr += sample_psnr
            total_ssim += sample_ssim

            # Generate 3-Panel Stitched Image
            panel_img = create_3panel_comparison_image(
                input_pil=low_pil,
                output_pil=output_pil,
                gt_pil=high_pil,
                font=font
            )
            panel_img.save(comp_file, quality=95)

            if (i + 1) % 100 == 0 or (i + 1) == total_images:
                curr_psnr = total_psnr / (i + 1)
                curr_ssim = total_ssim / (i + 1)
                print(f"  [{i + 1:4d}/{total_images:4d}] Saved '{filename}' | Running PSNR: {curr_psnr:.2f} dB, SSIM: {curr_ssim:.4f}", flush=True)

    avg_psnr = total_psnr / total_images
    avg_ssim = total_ssim / total_images

    print(f"\n==================================================")
    print(f"All {total_images} 3-Panel Comparisons and Pairs Successfully Generated!")
    print(f"  - 3-Panel Comparisons : {os.path.abspath(comparisons_dir)}")
    print(f"  - Separate Pairs Dir  : {os.path.abspath(pairs_dir)}")
    print(f"Dataset Overall Average PSNR : {avg_psnr:.4f} dB")
    print(f"Dataset Overall Average SSIM : {avg_ssim:.4f}")
    print(f"==================================================")


# ==============================================================================
# Evaluation Routine
# ==============================================================================

def evaluate(args):
    if args.device:
        device = torch.device(args.device)
    elif torch.cuda.is_available():
        device = torch.device('cuda')
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device('mps')
    else:
        device = torch.device('cpu')

    print(f"==================================================")
    print(f"  LYT-Net Model Evaluation & Comparison Generator ")
    print(f"==================================================")
    print(f"Device          : {device}")
    print(f"Weights         : {args.weights}")
    print(f"Data Root       : {args.data_root}")
    print(f"Num Plots       : {args.num_images}")
    print(f"Output Dir      : {args.output_dir}")
    print(f"Comparisons Dir : {args.comparisons_dir}")
    print(f"Export Dir      : {args.export_dir}")
    print(f"==================================================")

    weights_path = args.weights
    candidates = [
        weights_path,
        os.path.join(SCRIPT_DIR, weights_path),
        os.path.join(os.path.dirname(SCRIPT_DIR), weights_path),
        os.path.join(os.path.dirname(SCRIPT_DIR), 'lytnet_from_scratch.pth'),
        'lytnet_from_scratch.pth',
        os.path.join(os.path.dirname(SCRIPT_DIR), 'best_model.pth'),
        'best_model.pth',
    ]
    resolved_weights = None
    for c in candidates:
        if c and os.path.isfile(c):
            resolved_weights = c
            break

    if resolved_weights is not None:
        print(f"Loading weights from: {resolved_weights}")
        model = load_model(resolved_weights, device=device)
        print(f"Model ({model.__class__.__name__}) weights successfully loaded.")
    else:
        print(f"[Warning] Weights file '{args.weights}' not found. Using initialized LYT model.")
        model = LYT().to(device)

    model.eval()

    # 1. Evaluate on test set and create the 5 detailed comparison plots
    test_dataset = CombinedLOLDataset(
        data_root=args.data_root,
        split='test',
        training=False,
        augment=False
    )
    total_test_samples = len(test_dataset)

    if total_test_samples > 0:
        os.makedirs(args.output_dir, exist_ok=True)
        enhanced_save_dir = os.path.join(args.output_dir, 'enhanced_images')
        os.makedirs(enhanced_save_dir, exist_ok=True)

        print("\nRunning inference over test set...")
        all_psnr = []
        all_ssim = []

        num_to_plot = min(args.num_images, total_test_samples)
        plot_indices = set(np.linspace(0, total_test_samples - 1, num_to_plot, dtype=int).tolist()) if num_to_plot > 1 else {0}

        saved_comparison_data = []

        with torch.no_grad():
            for idx in range(total_test_samples):
                low, high = test_dataset[idx]
                low_batch = low.unsqueeze(0).to(device)
                high_batch = high.unsqueeze(0).to(device)

                output = model(low_batch)
                output = torch.clamp(output, 0.0, 1.0)

                psnr_val = calculate_psnr(output, high_batch, gt_mean=args.gt_mean)
                ssim_val = calculate_ssim(output, high_batch, gt_mean=args.gt_mean)
                all_psnr.append(psnr_val)
                all_ssim.append(ssim_val)

                if idx in plot_indices:
                    sample_order = len(saved_comparison_data) + 1
                    inp_np = tensor_to_numpy_image(low)
                    enh_np = tensor_to_numpy_image(output.squeeze(0))
                    gt_np = tensor_to_numpy_image(high)

                    plot_filename = f"comparison_{sample_order}_sample_{idx + 1}.png"
                    plot_path = os.path.join(args.output_dir, plot_filename)
                    save_side_by_side_plot(inp_np, enh_np, gt_np, psnr_val, ssim_val, plot_path, sample_idx=idx + 1)

                    enhanced_img_path = os.path.join(enhanced_save_dir, f"enhanced_{sample_order}_sample_{idx + 1}.png")
                    Image.fromarray((enh_np * 255).astype(np.uint8)).save(enhanced_img_path)

                    saved_comparison_data.append({
                        'idx': idx + 1,
                        'input': inp_np,
                        'enhanced': enh_np,
                        'gt': gt_np,
                        'psnr': psnr_val,
                        'ssim': ssim_val
                    })
                    print(f"  [Saved 5-Plot #{sample_order}/{num_to_plot}] Sample #{idx + 1:3d} -> {plot_filename} (PSNR: {psnr_val:.2f} dB, SSIM: {ssim_val:.4f})")

        if len(saved_comparison_data) > 0:
            master_grid_path = os.path.join(args.output_dir, f"all_{len(saved_comparison_data)}_comparisons_grid.png")
            save_all_comparisons_grid(saved_comparison_data, master_grid_path)
            print(f"\n[Saved Grid] Master comparison grid -> {master_grid_path}")

        avg_psnr = float(np.mean(all_psnr))
        avg_ssim = float(np.mean(all_ssim))
        print(f"\nValidation Summary: Test PSNR = {avg_psnr:.4f} dB | Test SSIM = {avg_ssim:.4f}")

    # 2. Always generate all 1,000+ 3-panel comparisons and pairs if flag or default is active
    if args.export_all_pairs or args.generate_all_comparisons:
        export_all_comparisons_and_pairs(
            model=model,
            data_root=args.data_root,
            comparisons_dir=args.comparisons_dir,
            pairs_dir=args.export_dir,
            device=device,
            gt_mean=args.gt_mean
        )


def build_parser():
    parser = argparse.ArgumentParser(description="Evaluate LYT-Net and generate side-by-side comparison plots.")
    parser.add_argument('--weights', type=str, default='lytnet_from_scratch.pth', help='Path to model weights (default: lytnet_from_scratch.pth)')
    parser.add_argument('--data_root', type=str, default='data', help='Root dataset directory')
    parser.add_argument('--num_images', type=int, default=5, help='Number of test plots to generate (default: 5)')
    parser.add_argument('--output_dir', type=str, default='results/comparisons', help='Directory for test comparison plots')
    parser.add_argument('--device', type=str, default=None, help='Device: cuda, mps, or cpu')
    parser.add_argument('--gt_mean', action='store_true', default=True, help='Enable GT mean adjustment')
    parser.add_argument('--no_gt_mean', dest='gt_mean', action='store_false', help='Disable GT mean adjustment')
    parser.add_argument('--export_all_pairs', action='store_true', default=True, help='Export pairs and 3-panel comparisons across all dataset images')
    parser.add_argument('--generate_all_comparisons', action='store_true', default=True, help='Generate 3-panel side-by-side images for all dataset images')
    parser.add_argument('--comparisons_dir', type=str, default='results/all_1000_comparisons', help='Output folder for all 3-panel comparison images')
    parser.add_argument('--export_dir', type=str, default='results/all_1000_pairs', help='Output folder for separated pairs (input, output, ground_truth)')
    return parser


if __name__ == '__main__':
    args = build_parser().parse_args()
    evaluate(args)
