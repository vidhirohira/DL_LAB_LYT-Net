import math
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    from pytorch_msssim import ssim as msssim_ssim
    _HAS_PYTORCH_MSSSIM = True
except ImportError:
    _HAS_PYTORCH_MSSSIM = False


# ==============================================================================
# 1. Native Differentiable SSIM Implementation
# ==============================================================================
def _gaussian_kernel_1d(window_size, sigma):
    coords = torch.arange(window_size, dtype=torch.float32) - window_size // 2
    g = torch.exp(-(coords ** 2) / (2 * sigma ** 2))
    return g / g.sum()

def _create_gaussian_window_2d(window_size=11, channel=3, sigma=1.5):
    g1d = _gaussian_kernel_1d(window_size, sigma).unsqueeze(1)
    g2d = g1d.mm(g1d.t()).unsqueeze(0).unsqueeze(0)
    window = g2d.expand(channel, 1, window_size, window_size).contiguous()
    return window

def native_ssim(img1, img2, window_size=11, sigma=1.5, data_range=1.0, size_average=True):
    """
    Computes Structural Similarity Index (SSIM) between two image tensors in a fully
    differentiable manner across RGB channels using a 2D Gaussian filter.
    """
    channel = img1.size(1)
    window = _create_gaussian_window_2d(window_size, channel, sigma).to(img1.device).type(img1.dtype)

    mu1 = F.conv2d(img1, window, padding=window_size // 2, groups=channel)
    mu2 = F.conv2d(img2, window, padding=window_size // 2, groups=channel)

    mu1_sq = mu1.pow(2)
    mu2_sq = mu2.pow(2)
    mu1_mu2 = mu1 * mu2

    sigma1_sq = F.conv2d(img1 * img1, window, padding=window_size // 2, groups=channel) - mu1_sq
    sigma2_sq = F.conv2d(img2 * img2, window, padding=window_size // 2, groups=channel) - mu2_sq
    sigma12 = F.conv2d(img1 * img2, window, padding=window_size // 2, groups=channel) - mu1_mu2

    C1 = (0.01 * data_range) ** 2
    C2 = (0.03 * data_range) ** 2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2) + 1e-8)

    if size_average:
        return ssim_map.mean()
    else:
        return ssim_map.mean(dim=(1, 2, 3))


# ==============================================================================
# 2. Individual Loss Components
# ==============================================================================

def smooth_l1_loss(y_pred, y_true, beta=1.0):
    """
    Smooth L1 (Huber) loss between prediction and ground truth.
    Less sensitive to outliers than L2 and smoother than L1 near 0.
    """
    return F.smooth_l1_loss(y_pred, y_true, beta=beta)


def ssim_loss(y_pred, y_true, data_range=1.0):
    """
    SSIM loss defined as: 1.0 - SSIM(y_pred, y_true).
    Ranges from 0.0 (identical structure) to ~2.0.
    """
    if _HAS_PYTORCH_MSSSIM:
        ssim_val = msssim_ssim(y_pred, y_true, data_range=data_range, size_average=True)
    else:
        ssim_val = native_ssim(y_pred, y_true, data_range=data_range, size_average=True)
    return 1.0 - ssim_val


def cosine_color_loss(y_pred, y_true, eps=1e-8):
    """
    Cosine Color Similarity Loss:
    Measures chromaticity / hue alignment by evaluating the cosine similarity
    between 3D RGB color vectors at each pixel location.
    
    Cosine similarity is 1.0 when the color directions match exactly.
    The loss is defined as: 1.0 - mean(cosine_similarity(y_pred, y_true, dim=1))
    """
    # y_pred, y_true shape: (B, 3, H, W)
    # Cosine similarity along color channel dimension (dim=1)
    cos_sim = F.cosine_similarity(y_pred, y_true, dim=1, eps=eps)
    return torch.mean(1.0 - cos_sim)


def horizontal_gradient_edge_loss(y_pred, y_true):
    """
    Horizontal Gradient Edge Loss:
    Captures edge transitions and structural sharpness along the horizontal axis (width dimension).
    
    grad_h(I) = I[:, :, :, 1:] - I[:, :, :, :-1]
    Loss is the L1 discrepancy between predicted and target horizontal gradients.
    """
    # Shape: (B, C, H, W-1)
    grad_h_pred = y_pred[:, :, :, 1:] - y_pred[:, :, :, :-1]
    grad_h_true = y_true[:, :, :, 1:] - y_true[:, :, :, :-1]
    return F.l1_loss(grad_h_pred, grad_h_true)


# ==============================================================================
# 3. Custom Hybrid Loss Module
# ==============================================================================

class HybridLoss(nn.Module):
    """
    Custom Hybrid Loss combining:
    1. Smooth L1 Loss (pixel-level fidelity)
    2. SSIM Loss (structural similarity & perceptual luminance/contrast)
    3. Cosine Color Similarity Loss (hue/chromaticity constancy)
    4. Horizontal Gradient Edge Loss (high-frequency horizontal edge sharpness)
    
    Formula:
        Total = w_l1 * L_SmoothL1 + w_ssim * L_SSIM + w_color * L_Color + w_grad_h * L_GradH
    """
    def __init__(self, w_l1=1.0, w_ssim=1.0, w_color=0.5, w_grad_h=0.5, device=None):
        super(HybridLoss, self).__init__()
        self.w_l1 = float(w_l1)
        self.w_ssim = float(w_ssim)
        self.w_color = float(w_color)
        self.w_grad_h = float(w_grad_h)
        self.last_losses = {}

    def forward(self, y_pred, y_true):
        """
        Args:
            y_pred (torch.Tensor): Model output of shape (B, 3, H, W), range [0, 1].
            y_true (torch.Tensor): Ground truth of shape (B, 3, H, W), range [0, 1].
        
        Returns:
            torch.Tensor: Scalar hybrid loss.
        """
        l_smooth_l1 = smooth_l1_loss(y_pred, y_true)
        l_ssim = ssim_loss(y_pred, y_true)
        l_color = cosine_color_loss(y_pred, y_true)
        l_grad_h = horizontal_gradient_edge_loss(y_pred, y_true)

        total_loss = (self.w_l1 * l_smooth_l1 +
                      self.w_ssim * l_ssim +
                      self.w_color * l_color +
                      self.w_grad_h * l_grad_h)

        # Record individual loss values for logging and monitoring
        self.last_losses = {
            'total': total_loss.item(),
            'smooth_l1': l_smooth_l1.item(),
            'ssim': l_ssim.item(),
            'color': l_color.item(),
            'grad_h': l_grad_h.item()
        }

        return total_loss

    def get_last_losses(self):
        """Returns the individual loss breakdown from the most recent forward pass."""
        return self.last_losses


# Alias for seamless drop-in replacement
CombinedLoss = HybridLoss
