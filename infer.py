#!/usr/bin/env python3
"""
Single-Image Inference & Live Viva Demonstration Tool for LYT-Net
Supports:
  1. CLI Single-Image Enhancement:
     python infer.py --image path/to/dark.png --output enhanced.png --side_by_side
  2. Interactive Gradio Web UI for Live Viva Demos:
     python infer.py --gradio
"""

import os
import sys
import time
import argparse
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF

# Optional HEIC support for iPhone low-light photos
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Ensure PyTorch directory is importable
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTORCH_DIR = os.path.join(SCRIPT_DIR, 'PyTorch')
if PYTORCH_DIR not in sys.path:
    sys.path.insert(0, PYTORCH_DIR)

from model import LYT, LYTNet, load_model


def get_default_device():
    """Auto-detects the fastest available device (CUDA, MPS, or CPU)."""
    if torch.cuda.is_available():
        return torch.device('cuda')
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return torch.device('mps')
    return torch.device('cpu')


def resolve_weights(weights_arg=None):
    """Locates the trained checkpoint, prioritizing the 100-epoch weights."""
    candidates = []
    if weights_arg:
        candidates.append(weights_arg)
        candidates.append(os.path.join(SCRIPT_DIR, weights_arg))

    # Preferred 100-epoch weights
    candidates.extend([
        os.path.join(SCRIPT_DIR, 'lytnet_from_scratch.pth'),
        'lytnet_from_scratch.pth',
        os.path.join(SCRIPT_DIR, 'best_model.pth'),
        'best_model.pth',
    ])

    for c in candidates:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def get_font(font_size=18):
    """Loads a standard clean font for labeling."""
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


def create_side_by_side(input_pil, output_pil, header_h=36, margin=8):
    """Creates a side-by-side [Low-Light Input | LYT-Net Output] comparison image."""
    font = get_font(16)
    w, h = input_pil.size
    if output_pil.size != (w, h):
        output_pil = output_pil.resize((w, h), Image.Resampling.BILINEAR)

    total_w = w * 2 + margin * 3
    total_h = h + header_h + margin * 2

    canvas = Image.new('RGB', (total_w, total_h), color=(24, 24, 27))
    draw = ImageDraw.Draw(canvas)

    panels = [
        ("Low-Light Input", input_pil, margin),
        ("LYT-Net Enhanced Output", output_pil, margin * 2 + w)
    ]

    for title, img, x_offset in panels:
        # Header banner
        header_rect = [x_offset, margin, x_offset + w, margin + header_h]
        draw.rectangle(header_rect, fill=(39, 39, 42))

        # Centered title text
        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = x_offset + (w - text_w) // 2
        text_y = margin + (header_h - text_h) // 2
        draw.text((text_x, text_y), title, fill=(245, 245, 245), font=font)

        # Paste image
        canvas.paste(img, (x_offset, margin + header_h))

    return canvas


def enhance_image(pil_img, model, device):
    """
    Runs model inference on a PIL image, handling reflection padding to multiple of 8.
    Returns: (enhanced_pil, inference_time_seconds)
    """
    if pil_img.mode != 'RGB':
        pil_img = pil_img.convert('RGB')

    img_tensor = TF.to_tensor(pil_img).unsqueeze(0)
    _, _, h, w = img_tensor.shape

    # Reflection padding to multiple of 8 for multiscale attention/CWD
    pad_h = (8 - h % 8) % 8
    pad_w = (8 - w % 8) % 8
    if pad_h > 0 or pad_w > 0:
        padded = F.pad(img_tensor, (0, pad_w, 0, pad_h), mode='reflect')
    else:
        padded = img_tensor

    padded = padded.to(device)

    start_t = time.perf_counter()
    with torch.no_grad():
        out = model(padded)
        out = torch.clamp(out, 0.0, 1.0)
    inference_time = time.perf_counter() - start_t

    if pad_h > 0 or pad_w > 0:
        out = out[:, :, :h, :w]

    out_np = (out.squeeze(0).permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)
    enhanced_pil = Image.fromarray(out_np)
    return enhanced_pil, inference_time


# ==============================================================================
# Gradio Web UI
# ==============================================================================

def launch_gradio_demo(model, device, weights_name="LYT-Net"):
    try:
        import gradio as gr
    except ImportError:
        print("[Error] Gradio is not installed. Install it via: pip install gradio")
        sys.exit(1)

    # Collect sample test images if available
    sample_images = []
    test_dirs = [
        os.path.join(SCRIPT_DIR, 'data', 'LOLv1', 'Test', 'input'),
        os.path.join(SCRIPT_DIR, 'data', 'LOLv1', 'test', 'input'),
        os.path.join(SCRIPT_DIR, 'data', 'LOLv2', 'Real_captured', 'Test', 'Low'),
    ]
    for d in test_dirs:
        if os.path.isdir(d):
            files = sorted([os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
            sample_images.extend(files[:6])
            if len(sample_images) >= 6:
                break

    def predict_fn(input_image):
        if input_image is None:
            return None, None, "Please upload or select an image."
        if not isinstance(input_image, Image.Image):
            input_image = Image.fromarray(input_image)

        w, h = input_image.size
        enhanced, elapsed = enhance_image(input_image, model, device)
        side_by_side = create_side_by_side(input_image, enhanced)
        status = f"Resolution: {w}x{h} | Latency: {elapsed*1000:.1f} ms | Device: {device} | Model: {weights_name}"
        return enhanced, side_by_side, status

    custom_css = """
    .gradio-container { max-width: 1200px !important; }
    .hero-title { text-align: center; font-size: 2.2rem; font-weight: 700; margin-bottom: 0.2rem; }
    .hero-sub { text-align: center; color: #64748b; font-size: 1.05rem; margin-bottom: 1.5rem; }
    """

    with gr.Blocks(title="LYT-Net Low-Light Image Enhancement", css=custom_css) as demo:
        gr.Markdown(
            """
            # LYT-Net: Low-Light Image Enhancement
            ### Lightweight YUV-Decomposition Network with Multi-Head Self-Attention
            *Trained for 100 Epochs with 4-Term Hybrid Loss (Smooth L1 + SSIM + Cosine Color + Gradient Edge Loss)*
            """
        )

        with gr.Row():
            with gr.Column(scale=1):
                input_img = gr.Image(type="pil", label="Low-Light Input Image", sources=["upload", "clipboard"])
                enhance_btn = gr.Button("Enhance Image", variant="primary", size="lg")
                status_box = gr.Textbox(label="Inference Telemetry", interactive=False)

            with gr.Column(scale=1):
                enhanced_output = gr.Image(type="pil", label="Enhanced Result")

        with gr.Row():
            side_by_side_output = gr.Image(type="pil", label="Side-by-Side Comparison")

        if sample_images:
            gr.Examples(
                examples=sample_images,
                inputs=input_img,
                label="Quick Demo Test Samples (from LOL Dataset)"
            )

        enhance_btn.click(
            fn=predict_fn,
            inputs=[input_img],
            outputs=[enhanced_output, side_by_side_output, status_box]
        )
        input_img.change(
            fn=predict_fn,
            inputs=[input_img],
            outputs=[enhanced_output, side_by_side_output, status_box]
        )

    print("\n========================================================")
    print("Launching LYT-Net Interactive Gradio UI...")
    print(f"Device: {device} | Weights: {weights_name}")
    print("========================================================")
    demo.launch(inbrowser=True, share=False)


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="LYT-Net Single-Image Inference & Viva Demo")
    parser.add_argument('--image', type=str, default=None, help='Path to single low-light image for enhancement')
    parser.add_argument('--output', type=str, default='enhanced_output.png', help='Path to save enhanced image')
    parser.add_argument('--weights', type=str, default=None, help='Path to checkpoint weights (.pth)')
    parser.add_argument('--side_by_side', action='store_true', default=True, help='Save side-by-side comparison')
    parser.add_argument('--device', type=str, default=None, help='Device: cuda, mps, or cpu')
    parser.add_argument('--gradio', action='store_true', help='Launch interactive Gradio demo web UI')
    args = parser.parse_args()

    # Determine device
    if args.device:
        device = torch.device(args.device)
    else:
        device = get_default_device()

    # Locate weights
    weights_path = resolve_weights(args.weights)
    if weights_path is None or not os.path.isfile(weights_path):
        print(f"[Error] Could not find weights at '{args.weights}'.")
        print("Please ensure 'lytnet_from_scratch.pth' or 'best_model.pth' is present in workspace.")
        sys.exit(1)

    print(f"[Loading Model] Checkpoint: {weights_path} | Target Device: {device}")
    model = load_model(weights_path, device=device)
    model.eval()
    print(f"[Model Loaded] Architecture: {model.__class__.__name__}")

    # Mode 1: Interactive Gradio Demo
    if args.gradio or (args.image is None and not sys.stdin.isatty()):
        launch_gradio_demo(model, device, weights_name=os.path.basename(weights_path))
        return

    # If no image specified and run from interactive terminal without --image, prompt or open gradio
    if args.image is None:
        print("\nNo input image provided.")
        print("Usage:")
        print("  CLI mode   : python infer.py --image path/to/dark.png --output result.png")
        print("  Gradio UI  : python infer.py --gradio")
        print("\nLaunching Gradio Demo interface by default...")
        launch_gradio_demo(model, device, weights_name=os.path.basename(weights_path))
        return

    # Mode 2: CLI Image Enhancement
    if not os.path.isfile(args.image):
        print(f"[Error] Input image '{args.image}' not found.")
        sys.exit(1)

    input_pil = Image.open(args.image)
    print(f"[Processing] Enhancing '{args.image}' (Resolution: {input_pil.size[0]}x{input_pil.size[1]})...")
    enhanced_pil, elapsed = enhance_image(input_pil, model, device)

    # Save output
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    enhanced_pil.save(args.output)
    print(f"[Success] Enhanced image saved to: {os.path.abspath(args.output)}")
    print(f"          Inference Latency      : {elapsed*1000:.1f} ms")

    if args.side_by_side:
        out_root, out_ext = os.path.splitext(args.output)
        sbs_path = f"{out_root}_comparison{out_ext or '.png'}"
        sbs_pil = create_side_by_side(input_pil, enhanced_pil)
        sbs_pil.save(sbs_path)
        print(f"          Side-by-Side Comparison: {os.path.abspath(sbs_path)}")


if __name__ == '__main__':
    main()
