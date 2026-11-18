import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.init as init

class LayerNormalization(nn.Module):
    def __init__(self, dim):
        super(LayerNormalization, self).__init__()
        self.norm = nn.LayerNorm(dim)

    def forward(self, x):
        # Rearrange the tensor for LayerNorm (B, C, H, W) to (B, H, W, C)
        x = x.permute(0, 2, 3, 1)
        x = self.norm(x)
        # Rearrange back to (B, C, H, W)
        return x.permute(0, 3, 1, 2)

class SEBlock(nn.Module):
    def __init__(self, input_channels, reduction_ratio=16):
        super(SEBlock, self).__init__()
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Linear(input_channels, input_channels // reduction_ratio)
        self.fc2 = nn.Linear(input_channels // reduction_ratio, input_channels)
        self._init_weights()

    def forward(self, x):
        batch_size, num_channels, _, _ = x.size()
        y = self.pool(x).reshape(batch_size, num_channels)
        y = F.relu(self.fc1(y))
        y = torch.tanh(self.fc2(y))
        y = y.reshape(batch_size, num_channels, 1, 1)
        return x * y
    
    def _init_weights(self):
        init.kaiming_uniform_(self.fc1.weight, a=0, mode='fan_in', nonlinearity='relu')
        init.kaiming_uniform_(self.fc2.weight, a=0, mode='fan_in', nonlinearity='relu')
        init.constant_(self.fc1.bias, 0)
        init.constant_(self.fc2.bias, 0)

class MSEFBlock(nn.Module):
    def __init__(self, filters):
        super(MSEFBlock, self).__init__()
        self.layer_norm = LayerNormalization(filters)
        self.depthwise_conv = nn.Conv2d(filters, filters, kernel_size=3, padding=1, groups=filters)
        self.se_attn = SEBlock(filters)
        self._init_weights()

    def forward(self, x):
        x_norm = self.layer_norm(x)
        x1 = self.depthwise_conv(x_norm)
        x2 = self.se_attn(x_norm)
        x_fused = x1 * x2
        x_out = x_fused + x
        return x_out
    
    def _init_weights(self):
        init.kaiming_uniform_(self.depthwise_conv.weight, a=0, mode='fan_in', nonlinearity='relu')
        init.constant_(self.depthwise_conv.bias, 0)

class MultiHeadSelfAttention(nn.Module):
    def __init__(self, embed_size, num_heads):
        super(MultiHeadSelfAttention, self).__init__()
        self.embed_size = embed_size
        self.num_heads = num_heads
        assert embed_size % num_heads == 0
        self.head_dim = embed_size // num_heads
        self.query_dense = nn.Linear(embed_size, embed_size)
        self.key_dense = nn.Linear(embed_size, embed_size)
        self.value_dense = nn.Linear(embed_size, embed_size)
        self.combine_heads = nn.Linear(embed_size, embed_size)
        self._init_weights()

    def split_heads(self, x, batch_size):
        x = x.reshape(batch_size, -1, self.num_heads, self.head_dim)
        return x.permute(0, 2, 1, 3)

    def forward(self, x):
        batch_size, _, height, width = x.size()
        x = x.reshape(batch_size, height * width, -1)

        query = self.split_heads(self.query_dense(x), batch_size)
        key = self.split_heads(self.key_dense(x), batch_size)
        value = self.split_heads(self.value_dense(x), batch_size)
        
        attention_weights = F.softmax(torch.matmul(query, key.transpose(-2, -1)) / (self.head_dim ** 0.5), dim=-1)
        attention = torch.matmul(attention_weights, value)
        attention = attention.permute(0, 2, 1, 3).contiguous().reshape(batch_size, -1, self.embed_size)
        
        output = self.combine_heads(attention)
        
        return output.reshape(batch_size, height, width, self.embed_size).permute(0, 3, 1, 2)

    def _init_weights(self):
        init.xavier_uniform_(self.query_dense.weight)
        init.xavier_uniform_(self.key_dense.weight)
        init.xavier_uniform_(self.value_dense.weight)
        init.xavier_uniform_(self.combine_heads.weight)
        init.constant_(self.query_dense.bias, 0)
        init.constant_(self.key_dense.bias, 0)
        init.constant_(self.value_dense.bias, 0)
        init.constant_(self.combine_heads.bias, 0)

class Denoiser(nn.Module):
    def __init__(self, num_filters, kernel_size=3, activation='relu'):
        super(Denoiser, self).__init__()
        self.conv1 = nn.Conv2d(1, num_filters, kernel_size=kernel_size, padding=1)
        self.conv2 = nn.Conv2d(num_filters, num_filters, kernel_size=kernel_size, stride=2, padding=1)
        self.conv3 = nn.Conv2d(num_filters, num_filters, kernel_size=kernel_size, stride=2, padding=1)
        self.conv4 = nn.Conv2d(num_filters, num_filters, kernel_size=kernel_size, stride=2, padding=1)
        self.bottleneck = MultiHeadSelfAttention(embed_size=num_filters, num_heads=4)
        self.up2 = nn.Upsample(scale_factor=2, mode='nearest')
        self.up3 = nn.Upsample(scale_factor=2, mode='nearest')
        self.up4 = nn.Upsample(scale_factor=2, mode='nearest')
        self.output_layer = nn.Conv2d(1, 1, kernel_size=kernel_size, padding=1)
        self.res_layer = nn.Conv2d(num_filters, 1, kernel_size=kernel_size, padding=1)
        self.activation = getattr(F, activation)
        self._init_weights()

    def forward(self, x):
        x1 = self.activation(self.conv1(x))
        x2 = self.activation(self.conv2(x1))
        x3 = self.activation(self.conv3(x2))
        x4 = self.activation(self.conv4(x3))
        x = self.bottleneck(x4)
        x = self.up4(x)
        x = self.up3(x + x3)
        x = self.up2(x + x2)
        x = x + x1
        x = self.res_layer(x)
        return torch.tanh(self.output_layer(x + x))
    
    def _init_weights(self):
        for layer in [self.conv1, self.conv2, self.conv3, self.conv4, self.output_layer, self.res_layer]:
            init.kaiming_uniform_(layer.weight, a=0, mode='fan_in', nonlinearity='relu')
            if layer.bias is not None:
                init.constant_(layer.bias, 0)

class LYT(nn.Module):
    def __init__(self, filters=32):
        super(LYT, self).__init__()
        self.process_y = self._create_processing_layers(filters)
        self.process_cb = self._create_processing_layers(filters)
        self.process_cr = self._create_processing_layers(filters)

        self.denoiser_cb = Denoiser(filters // 2)
        self.denoiser_cr = Denoiser(filters // 2)
        self.lum_pool = nn.MaxPool2d(8)
        self.lum_mhsa = MultiHeadSelfAttention(embed_size=filters, num_heads=4)
        self.lum_up = nn.Upsample(scale_factor=8, mode='nearest')
        self.lum_conv = nn.Conv2d(filters, filters, kernel_size=1, padding=0)
        self.ref_conv = nn.Conv2d(filters * 2, filters, kernel_size=1, padding=0)
        self.msef = MSEFBlock(filters)
        self.recombine = nn.Conv2d(filters * 2, filters, kernel_size=3, padding=1)
        self.final_adjustments = nn.Conv2d(filters, 3, kernel_size=3, padding=1)
        self._init_weights()

    def _create_processing_layers(self, filters):
        return nn.Sequential(
            nn.Conv2d(1, filters, kernel_size=3, padding=1),
            nn.ReLU(inplace=True)
        )
    
    def _rgb_to_ycbcr(self, image):
        r, g, b = image[:, 0, :, :], image[:, 1, :, :], image[:, 2, :, :]
    
        y = 0.299 * r + 0.587 * g + 0.114 * b
        u = -0.14713 * r - 0.28886 * g + 0.436 * b + 0.5
        v = 0.615 * r - 0.51499 * g - 0.10001 * b + 0.5
        
        yuv = torch.stack((y, u, v), dim=1)
        return yuv

    def forward(self, inputs):
        ycbcr = self._rgb_to_ycbcr(inputs)
        y, cb, cr = torch.split(ycbcr, 1, dim=1)
        cb = self.denoiser_cb(cb) + cb
        cr = self.denoiser_cr(cr) + cr

        y_processed = self.process_y(y)
        cb_processed = self.process_cb(cb)
        cr_processed = self.process_cr(cr)

        ref = torch.cat([cb_processed, cr_processed], dim=1)
        lum = y_processed
        lum_1 = self.lum_pool(lum)
        lum_1 = self.lum_mhsa(lum_1)
        lum_1 = self.lum_up(lum_1)
        lum = lum + lum_1

        ref = self.ref_conv(ref)
        shortcut = ref
        ref = ref + 0.2 * self.lum_conv(lum)
        ref = self.msef(ref)
        ref = ref + shortcut

        recombined = self.recombine(torch.cat([ref, lum], dim=1))
        output = self.final_adjustments(recombined)
        return torch.sigmoid(output)
    
    def _init_weights(self):
        for module in self.children():
            if isinstance(module, nn.Conv2d) or isinstance(module, nn.Linear):
                init.kaiming_uniform_(module.weight, a=0, mode='fan_in', nonlinearity='relu')
                if module.bias is not None:
                    init.constant_(module.bias, 0)


# ==============================================================================
# Lightweight YUV Transformer (LYTNet) - 100-Epoch Notebook Architecture (~45K Params)
# ==============================================================================

def rgb_to_yuv(img):
    r, g, b = img[:, 0:1], img[:, 1:2], img[:, 2:3]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    u = -0.14713 * r - 0.28886 * g + 0.436 * b
    v = 0.615 * r - 0.51499 * g - 0.10001 * b
    return y, torch.cat([u, v], dim=1)

def yuv_to_rgb(y, uv):
    u, v = uv[:, 0:1], uv[:, 1:2]
    r = y + 1.13983 * v
    g = y - 0.39465 * u - 0.58060 * v
    b = y + 2.03211 * u
    return torch.clamp(torch.cat([r, g, b], dim=1), 0.0, 1.0)

class MSEFBlockCustom(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.norm = nn.LayerNorm(channels)
        self.dwconv = nn.Conv2d(channels, channels, kernel_size=3, padding=1, groups=channels)
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, max(channels // 4, 4), 1),
            nn.ReLU(inplace=True),
            nn.Conv2d(max(channels // 4, 4), channels, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        b, c, h, w = x.shape
        x_norm = self.norm(x.permute(0, 2, 3, 1)).permute(0, 3, 1, 2)
        feat = self.dwconv(x_norm)
        scale = self.se(feat)
        return feat * scale + x

class LightweightMHSA(nn.Module):
    def __init__(self, channels, heads=4, pool_size=16):
        super().__init__()
        self.pool = nn.AdaptiveAvgPool2d((pool_size, pool_size))
        self.attn = nn.MultiheadAttention(embed_dim=channels, num_heads=heads, batch_first=True)
        self.proj = nn.Conv2d(channels, channels, 1)

    def forward(self, x):
        b, c, h, w = x.shape
        if x.device.type == 'mps':
            try:
                x_small = self.pool(x)
            except RuntimeError:
                x_small = self.pool(x.cpu()).to(x.device)
        else:
            x_small = self.pool(x)

        _, _, sh, sw = x_small.shape
        tokens = x_small.flatten(2).transpose(1, 2)
        attn_out, _ = self.attn(tokens, tokens, tokens)
        attn_map = attn_out.transpose(1, 2).reshape(b, c, sh, sw)
        up = F.interpolate(attn_map, size=(h, w), mode='bilinear', align_corners=False)
        return self.proj(up) + x

class CWDBlock(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1, groups=channels)
        self.pw1 = nn.Conv2d(channels, channels, 1)
        self.act = nn.GELU()
        self.msef = MSEFBlockCustom(channels)

    def forward(self, x):
        out = self.act(self.pw1(self.conv1(x)))
        return self.msef(out + x)

class LYTNet(nn.Module):
    def __init__(self, dim=24):
        super().__init__()
        self.dim = dim
        self.y_in = nn.Conv2d(1, dim, 3, padding=1)
        self.y_cwd1 = CWDBlock(dim)
        self.y_mhsa = LightweightMHSA(dim, heads=4, pool_size=16)
        self.y_cwd2 = CWDBlock(dim)
        self.y_out = nn.Conv2d(dim, 1, 3, padding=1)

        self.uv_in = nn.Conv2d(2, dim, 3, padding=1)
        self.uv_cwd1 = CWDBlock(dim)
        self.uv_cwd2 = CWDBlock(dim)
        self.uv_out = nn.Conv2d(dim, 2, 3, padding=1)

        self.fusion = nn.Sequential(
            nn.Conv2d(3, dim, 3, padding=1),
            nn.GELU(),
            MSEFBlockCustom(dim),
            nn.Conv2d(dim, 3, 3, padding=1)
        )

    def forward(self, rgb):
        y, uv = rgb_to_yuv(rgb)
        fy = self.y_cwd2(self.y_mhsa(self.y_cwd1(self.y_in(y))))
        y_enh = y + self.y_out(fy)
        fuv = self.uv_cwd2(self.uv_cwd1(self.uv_in(uv)))
        uv_enh = uv + self.uv_out(fuv)
        rgb_init = yuv_to_rgb(y_enh, uv_enh)
        out = torch.clamp(rgb_init + self.fusion(rgb_init), 0.0, 1.0)
        return out


def load_model(weights_path='best_model.pth', device='cpu'):
    """
    Auto-detects whether the checkpoint belongs to LYTNet (dim=24) or LYT (repo original)
    and loads the corresponding weights.
    """
    device = torch.device(device)
    state = torch.load(weights_path, map_location=device)
    if isinstance(state, dict) and 'model_state_dict' in state:
        state = state['model_state_dict']

    if 'y_in.weight' in state:
        # User 100-epoch notebook architecture
        dim = state['y_in.weight'].shape[0]
        model = LYTNet(dim=dim).to(device)
    else:
        # Original repo architecture
        model = LYT().to(device)

    model.load_state_dict(state)
    model.eval()
    return model

                    