import os
import sys
import argparse
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.optim.lr_scheduler import CosineAnnealingLR

# Ensure local modules are importable regardless of launch directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from model import LYT
from losses import HybridLoss
from dataloader import create_dataloaders, discover_lol_datasets


# ==============================================================================
# Metric Calculations (PSNR & SSIM)
# ==============================================================================

def calculate_psnr(img1, img2, max_pixel_value=1.0, gt_mean=True):
    """
    Calculate PSNR (Peak Signal-to-Noise Ratio) between restored image and ground truth.

    Args:
        img1 (torch.Tensor): Restored image (BxCxHxW)
        img2 (torch.Tensor): Ground truth image (BxCxHxW)
        max_pixel_value (float): Dynamic range. Default is 1.0.
        gt_mean (bool): Standard LOL benchmark flag aligning mean brightness with target.
    """
    if gt_mean:
        img1_gray = img1.mean(dim=1, keepdim=True)
        img2_gray = img2.mean(dim=1, keepdim=True)

        mean_restored = img1_gray.mean() + 1e-8
        mean_target = img2_gray.mean()
        img1 = torch.clamp(img1 * (mean_target / mean_restored), 0.0, 1.0)

    mse = F.mse_loss(img1, img2, reduction='mean')
    if mse == 0:
        return float('inf')
    psnr = 20 * torch.log10(max_pixel_value / torch.sqrt(mse))
    return psnr.item()


def calculate_ssim(img1, img2, max_pixel_value=1.0, gt_mean=True):
    """
    Calculate SSIM (Structural Similarity Index) between two images.
    """
    if gt_mean:
        img1_gray = img1.mean(dim=1, keepdim=True)
        img2_gray = img2.mean(dim=1, keepdim=True)

        mean_restored = img1_gray.mean() + 1e-8
        mean_target = img2_gray.mean()
        img1 = torch.clamp(img1 * (mean_target / mean_restored), 0.0, 1.0)

    try:
        from torchmetrics.functional import structural_similarity_index_measure
        ssim_val = structural_similarity_index_measure(img1, img2, data_range=max_pixel_value)
        return ssim_val.item()
    except Exception:
        from losses import native_ssim
        return native_ssim(img1, img2, data_range=max_pixel_value).item()


def validate(model, dataloader, device, gt_mean=True):
    """
    Evaluates model on validation dataloader, computing average PSNR and SSIM.
    """
    model.eval()
    total_psnr = 0.0
    total_ssim = 0.0
    num_samples = len(dataloader)

    if num_samples == 0:
        return 0.0, 0.0

    with torch.no_grad():
        for low, high in dataloader:
            low = low.to(device)
            high = high.to(device)
            output = model(low)
            output = torch.clamp(output, 0.0, 1.0)

            total_psnr += calculate_psnr(output, high, gt_mean=gt_mean)
            total_ssim += calculate_ssim(output, high, gt_mean=gt_mean)

    avg_psnr = total_psnr / num_samples
    avg_ssim = total_ssim / num_samples
    return avg_psnr, avg_ssim


# ==============================================================================
# Main Training Routine
# ==============================================================================

def train(args):
    # Device selection: CUDA -> MPS -> CPU
    if args.device:
        device = torch.device(args.device)
    elif torch.cuda.is_available():
        device = torch.device('cuda')
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device('mps')
    else:
        device = torch.device('cpu')

    print(f"==================================================")
    print(f"  LYT-Net Training Pipeline (LOL-v1 + LOL-v2)    ")
    print(f"==================================================")
    print(f"Device        : {device}")
    print(f"Epochs        : {args.epochs}")
    print(f"Learning Rate : {args.lr}")
    print(f"Optimizer     : AdamW (weight_decay={args.weight_decay})")
    print(f"Scheduler     : CosineAnnealingLR (T_max={args.epochs}, eta_min={args.min_lr})")
    print(f"Batch Size    : {args.batch_size}")
    print(f"Crop Size     : {args.crop_size}")
    print(f"Data Root     : {args.data_root}")
    print(f"Save Path     : {args.save_path}")
    print(f"==================================================")

    # 1. Discover Datasets & Create Combined Loaders
    _, stats = discover_lol_datasets(args.data_root)
    print(f"Dataset Discovery Summary under '{stats['root']}':")
    print(f"  - LOL-v1 Train        : {stats['LOLv1_train']} pairs | Test: {stats['LOLv1_test']} pairs")
    print(f"  - LOL-v2 Real Train   : {stats['LOLv2_Real_train']} pairs | Test: {stats['LOLv2_Real_test']} pairs")
    print(f"  - LOL-v2 Syn Train    : {stats['LOLv2_Synthetic_train']} pairs | Test: {stats['LOLv2_Synthetic_test']} pairs")

    train_loader, test_loader = create_dataloaders(
        data_root=args.data_root,
        crop_size=args.crop_size,
        batch_size=args.batch_size,
        num_workers=args.num_workers
    )

    if train_loader is None or len(train_loader) == 0:
        print(f"\n[ERROR] No training pairs found under '{args.data_root}'.")
        print("Please ensure your dataset is placed according to the folder structure:")
        print("  data/LOLv1/Train/{input, target}")
        print("  data/LOLv2/Real_captured/Train/{Low, Normal}")
        print("  data/LOLv2/Synthetic/Train/{Low, Normal}")
        return

    print(f"Combined Training Batches : {len(train_loader)} (Batch Size: {args.batch_size})")
    print(f"Combined Testing Samples  : {len(test_loader) if test_loader else 0}")
    print(f"==================================================")

    # 2. Model Initialization
    model = LYT().to(device)

    # 3. Custom Hybrid Loss
    criterion = HybridLoss(
        w_l1=args.w_l1,
        w_ssim=args.w_ssim,
        w_color=args.w_color,
        w_grad_h=args.w_grad_h,
        device=device
    )

    # 4. AdamW Optimizer & CosineAnnealingLR Scheduler
    optimizer = optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
        betas=(0.9, 0.999)
    )

    scheduler = CosineAnnealingLR(
        optimizer,
        T_max=args.epochs,
        eta_min=args.min_lr
    )

    # Use AMP GradScaler only for CUDA
    use_amp = (device.type == 'cuda')
    scaler = torch.amp.GradScaler('cuda') if use_amp else None

    # Resume from checkpoint if specified
    start_epoch = 0
    best_psnr = 0.0
    best_ssim = 0.0
    best_epoch = 0

    if args.resume and os.path.isfile(args.resume):
        print(f"Loading checkpoint from: {args.resume}")
        checkpoint = torch.load(args.resume, map_location=device)
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            model.load_state_dict(checkpoint['model_state_dict'])
            if 'optimizer_state_dict' in checkpoint:
                optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            if 'epoch' in checkpoint:
                start_epoch = checkpoint['epoch'] + 1
            if 'best_psnr' in checkpoint:
                best_psnr = checkpoint['best_psnr']
        else:
            model.load_state_dict(checkpoint)
        print(f"Resumed from epoch {start_epoch} (Best PSNR: {best_psnr:.4f})")

    # Ensure output directories exist
    save_dir = os.path.dirname(args.save_path)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    print("\nStarting training for 100 epochs...")
    start_time = time.time()

    for epoch in range(start_epoch, args.epochs):
        epoch_start = time.time()
        model.train()
        running_loss = 0.0
        running_sublosses = {'smooth_l1': 0.0, 'ssim': 0.0, 'color': 0.0, 'grad_h': 0.0}

        for batch_idx, (inputs, targets) in enumerate(train_loader):
            inputs = inputs.to(device)
            targets = targets.to(device)

            optimizer.zero_grad()

            if use_amp:
                with torch.amp.autocast('cuda'):
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                optimizer.step()

            running_loss += loss.item()
            sublosses = criterion.get_last_losses()
            for k in running_sublosses:
                running_sublosses[k] += sublosses.get(k, 0.0)

            if (batch_idx + 1) % 50 == 0 or (batch_idx + 1) == len(train_loader):
                print(f"  [Epoch {epoch + 1:2d} | Batch {batch_idx + 1:3d}/{len(train_loader):3d}] Loss: {loss.item():.4f}")

        # Average losses over batches
        num_batches = len(train_loader)
        epoch_loss = running_loss / num_batches
        avg_sublosses = {k: v / num_batches for k, v in running_sublosses.items()}
        current_lr = scheduler.get_last_lr()[0]

        # Step scheduler once per epoch
        scheduler.step()

        # Validation
        if test_loader is not None and len(test_loader) > 0 and (epoch + 1) % args.val_freq == 0:
            val_psnr, val_ssim = validate(model, test_loader, device, gt_mean=True)
        else:
            val_psnr, val_ssim = 0.0, 0.0

        epoch_duration = time.time() - epoch_start
        improved = val_psnr > best_psnr

        print(
            f"Epoch [{epoch + 1:3d}/{args.epochs:3d}] ({epoch_duration:.1f}s) | "
            f"LR: {current_lr:.6f} | "
            f"Loss: {epoch_loss:.4f} [L1:{avg_sublosses['smooth_l1']:.3f}, SSIM:{avg_sublosses['ssim']:.3f}, Col:{avg_sublosses['color']:.3f}, GrdH:{avg_sublosses['grad_h']:.3f}] | "
            f"Val PSNR: {val_psnr:.4f} dB | Val SSIM: {val_ssim:.4f}"
            f"{' [*BEST*]' if improved else ''}"
        )

        # Save best weights based on validation PSNR
        if improved:
            best_psnr = val_psnr
            best_ssim = val_ssim
            best_epoch = epoch + 1

            # Save raw model state_dict for evaluation / inference
            torch.save(model.state_dict(), args.save_path)

            # Save full training checkpoint
            ckpt = {
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'scheduler_state_dict': scheduler.state_dict(),
                'best_psnr': best_psnr,
                'best_ssim': best_ssim,
                'args': vars(args)
            }
            torch.save(ckpt, args.checkpoint_path)
            print(f"  --> Saved new best model to '{args.save_path}' (PSNR: {best_psnr:.4f} dB, SSIM: {best_ssim:.4f})")

    total_time = time.time() - start_time
    print(f"\n==================================================")
    print(f"Training Complete in {total_time / 60:.2f} minutes.")
    print(f"Best Validation PSNR : {best_psnr:.4f} dB (at epoch {best_epoch})")
    print(f"Best Validation SSIM : {best_ssim:.4f}")
    print(f"Best Weights Saved To: {os.path.abspath(args.save_path)}")
    print(f"==================================================")


def build_parser():
    parser = argparse.ArgumentParser(description="Train LYT-Net with Hybrid Loss on Combined LOL-v1 & LOL-v2")
    # Training Hyperparameters
    parser.add_argument('--epochs', type=int, default=100, help='Number of training epochs (default: 100)')
    parser.add_argument('--lr', type=float, default=3e-4, help='Initial learning rate for AdamW (default: 3e-4)')
    parser.add_argument('--min_lr', type=float, default=1e-6, help='Minimum LR for CosineAnnealingLR (default: 1e-6)')
    parser.add_argument('--weight_decay', type=float, default=1e-4, help='Weight decay for AdamW (default: 1e-4)')
    parser.add_argument('--batch_size', type=int, default=4, help='Batch size for training (default: 4)')
    parser.add_argument('--crop_size', type=int, default=256, help='Random crop dimension for training (default: 256)')

    # Loss Weights
    parser.add_argument('--w_l1', type=float, default=1.0, help='Weight for Smooth L1 loss (default: 1.0)')
    parser.add_argument('--w_ssim', type=float, default=1.0, help='Weight for SSIM loss (default: 1.0)')
    parser.add_argument('--w_color', type=float, default=0.5, help='Weight for Cosine Color loss (default: 0.5)')
    parser.add_argument('--w_grad_h', type=float, default=0.5, help='Weight for Horizontal Gradient loss (default: 0.5)')

    # Dataset & Paths
    parser.add_argument('--data_root', type=str, default='data', help='Root dataset directory (default: data)')
    parser.add_argument('--save_path', type=str, default='best_model.pth', help='Path to save best weights (default: best_model.pth)')
    parser.add_argument('--checkpoint_path', type=str, default='best_checkpoint.pth', help='Path to save full checkpoint (default: best_checkpoint.pth)')
    parser.add_argument('--resume', type=str, default=None, help='Path to checkpoint to resume training from')

    # Environment
    parser.add_argument('--device', type=str, default=None, help='Device: cuda, mps, or cpu (default: auto)')
    default_workers = 0 if sys.platform == 'darwin' else 2
    parser.add_argument('--num_workers', type=int, default=default_workers, help=f'DataLoader workers (default: {default_workers})')
    parser.add_argument('--val_freq', type=int, default=1, help='Epoch frequency for validation (default: 1)')

    return parser


if __name__ == '__main__':
    args = build_parser().parse_args()
    train(args)
