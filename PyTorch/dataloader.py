import os
import random
from PIL import Image
import torch
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as transforms
import torchvision.transforms.functional as TF

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.PNG', '.JPG', '.JPEG')

def is_image_file(filename):
    return filename.endswith(IMAGE_EXTENSIONS) and not filename.startswith('.')

def find_paired_images_in_dirs(low_dir, high_dir):
    """
    Finds and pairs matching low-light and normal-light image paths from two directories.
    Handles exact filename matches as well as sorted order matching.
    """
    if not (os.path.isdir(low_dir) and os.path.isdir(high_dir)):
        return []

    low_files = sorted([f for f in os.listdir(low_dir) if is_image_file(f)])
    high_files = sorted([f for f in os.listdir(high_dir) if is_image_file(f)])

    if not low_files or not high_files:
        return []

    # Strategy 1: Check for exact filename match
    high_files_set = set(high_files)
    matched_pairs = []
    has_exact_match = any(f in high_files_set for f in low_files)

    if has_exact_match:
        for f in low_files:
            if f in high_files_set:
                matched_pairs.append((os.path.join(low_dir, f), os.path.join(high_dir, f)))
        if len(matched_pairs) > 0:
            return matched_pairs

    # Strategy 2: Pair by sorted order if counts match
    if len(low_files) == len(high_files):
        return [(os.path.join(low_dir, lf), os.path.join(high_dir, hf))
                for lf, hf in zip(low_files, high_files)]

    # Strategy 3: Best effort matching by stem name
    high_stem_map = {os.path.splitext(f)[0]: f for f in high_files}
    for lf in low_files:
        stem = os.path.splitext(lf)[0]
        # Clean potential prefixes like 'low_', 'normal_', etc.
        stem_clean = stem.replace('low', '').replace('Normal', '').replace('normal', '').replace('target', '').strip('_')
        for h_stem, hf in high_stem_map.items():
            h_clean = h_stem.replace('low', '').replace('Normal', '').replace('normal', '').replace('target', '').strip('_')
            if stem_clean == h_clean and stem_clean != '':
                matched_pairs.append((os.path.join(low_dir, lf), os.path.join(high_dir, hf)))
                break

    return matched_pairs

def resolve_candidate_dirs(base_dir, candidates):
    """
    Returns the first directory among candidates that exists under base_dir.
    """
    for cand in candidates:
        full_path = os.path.join(base_dir, cand)
        if os.path.isdir(full_path):
            return full_path
    return None

def discover_lol_datasets(data_root='data'):
    """
    Discovers all LOL-v1 and LOL-v2 (Real_captured and Synthetic) image pairs
    under data_root for both 'train' and 'test' splits.
    
    Returns:
        dict: {
            'train': [(low_path, high_path), ...],
            'test':  [(low_path, high_path), ...]
        },
        dict: Summary of discovered counts per subset
    """
    # Look for data_root in several common relative paths
    search_roots = [
        data_root,
        os.path.join('PyTorch', data_root),
        os.path.join('..', data_root),
        os.path.join(os.path.dirname(__file__), 'data'),
        os.path.join(os.path.dirname(__file__), '..', 'data')
    ]
    actual_root = None
    for root in search_roots:
        if os.path.isdir(root):
            actual_root = root
            break

    if actual_root is None:
        actual_root = data_root

    dataset_pairs = {'train': [], 'test': []}
    stats = {
        'root': actual_root,
        'LOLv1_train': 0, 'LOLv1_test': 0,
        'LOLv2_Real_train': 0, 'LOLv2_Real_test': 0,
        'LOLv2_Synthetic_train': 0, 'LOLv2_Synthetic_test': 0,
        'other_train': 0, 'other_test': 0,
    }

    if not os.path.isdir(actual_root):
        return dataset_pairs, stats

    # 1. LOL-v1 Discovery
    # Train
    lolv1_train_low = resolve_candidate_dirs(actual_root, [
        'LOLv1/Train/input', 'LOLv1/train/input', 'LOLv1/Train/low', 'LOLv1/train/low',
        'lolv1/Train/input', 'lolv1/train/input', 'our485/low'
    ])
    lolv1_train_high = resolve_candidate_dirs(actual_root, [
        'LOLv1/Train/target', 'LOLv1/train/target', 'LOLv1/Train/high', 'LOLv1/train/high',
        'LOLv1/Train/normal', 'LOLv1/train/normal', 'lolv1/Train/target', 'our485/high'
    ])
    if lolv1_train_low and lolv1_train_high:
        pairs = find_paired_images_in_dirs(lolv1_train_low, lolv1_train_high)
        dataset_pairs['train'].extend(pairs)
        stats['LOLv1_train'] = len(pairs)

    # Test
    lolv1_test_low = resolve_candidate_dirs(actual_root, [
        'LOLv1/Test/input', 'LOLv1/test/input', 'LOLv1/Test/low', 'LOLv1/test/low',
        'lolv1/Test/input', 'lolv1/test/input', 'eval15/low'
    ])
    lolv1_test_high = resolve_candidate_dirs(actual_root, [
        'LOLv1/Test/target', 'LOLv1/test/target', 'LOLv1/Test/high', 'LOLv1/test/high',
        'LOLv1/Test/normal', 'LOLv1/test/normal', 'lolv1/Test/target', 'eval15/high'
    ])
    if lolv1_test_low and lolv1_test_high:
        pairs = find_paired_images_in_dirs(lolv1_test_low, lolv1_test_high)
        dataset_pairs['test'].extend(pairs)
        stats['LOLv1_test'] = len(pairs)

    # 2. LOL-v2 Real_captured Discovery
    lolv2_real_train_low = resolve_candidate_dirs(actual_root, [
        'LOLv2/Real_captured/Train/Low', 'LOLv2/Real_captured/train/low',
        'lolv2/Real_captured/Train/Low', 'LOLv2/Real_captured/Train/input',
        'LOLv2/Train/Low'
    ])
    lolv2_real_train_high = resolve_candidate_dirs(actual_root, [
        'LOLv2/Real_captured/Train/Normal', 'LOLv2/Real_captured/train/normal',
        'lolv2/Real_captured/Train/Normal', 'LOLv2/Real_captured/Train/target',
        'LOLv2/Train/Normal'
    ])
    if lolv2_real_train_low and lolv2_real_train_high:
        pairs = find_paired_images_in_dirs(lolv2_real_train_low, lolv2_real_train_high)
        dataset_pairs['train'].extend(pairs)
        stats['LOLv2_Real_train'] = len(pairs)

    lolv2_real_test_low = resolve_candidate_dirs(actual_root, [
        'LOLv2/Real_captured/Test/Low', 'LOLv2/Real_captured/test/low',
        'lolv2/Real_captured/Test/Low', 'LOLv2/Real_captured/Test/input',
        'LOLv2/Test/Low'
    ])
    lolv2_real_test_high = resolve_candidate_dirs(actual_root, [
        'LOLv2/Real_captured/Test/Normal', 'LOLv2/Real_captured/test/normal',
        'lolv2/Real_captured/Test/Normal', 'LOLv2/Real_captured/Test/target',
        'LOLv2/Test/Normal'
    ])
    if lolv2_real_test_low and lolv2_real_test_high:
        pairs = find_paired_images_in_dirs(lolv2_real_test_low, lolv2_real_test_high)
        dataset_pairs['test'].extend(pairs)
        stats['LOLv2_Real_test'] = len(pairs)

    # 3. LOL-v2 Synthetic Discovery
    lolv2_syn_train_low = resolve_candidate_dirs(actual_root, [
        'LOLv2/Synthetic/Train/Low', 'LOLv2/Synthetic/train/low',
        'lolv2/Synthetic/Train/Low', 'LOLv2/Synthetic/Train/input'
    ])
    lolv2_syn_train_high = resolve_candidate_dirs(actual_root, [
        'LOLv2/Synthetic/Train/Normal', 'LOLv2/Synthetic/train/normal',
        'lolv2/Synthetic/Train/Normal', 'LOLv2/Synthetic/Train/target'
    ])
    if lolv2_syn_train_low and lolv2_syn_train_high:
        pairs = find_paired_images_in_dirs(lolv2_syn_train_low, lolv2_syn_train_high)
        dataset_pairs['train'].extend(pairs)
        stats['LOLv2_Synthetic_train'] = len(pairs)

    lolv2_syn_test_low = resolve_candidate_dirs(actual_root, [
        'LOLv2/Synthetic/Test/Low', 'LOLv2/Synthetic/test/low',
        'lolv2/Synthetic/Test/Low', 'LOLv2/Synthetic/Test/input'
    ])
    lolv2_syn_test_high = resolve_candidate_dirs(actual_root, [
        'LOLv2/Synthetic/Test/Normal', 'LOLv2/Synthetic/test/normal',
        'lolv2/Synthetic/Test/Normal', 'LOLv2/Synthetic/Test/target'
    ])
    if lolv2_syn_test_low and lolv2_syn_test_high:
        pairs = find_paired_images_in_dirs(lolv2_syn_test_low, lolv2_syn_test_high)
        dataset_pairs['test'].extend(pairs)
        stats['LOLv2_Synthetic_test'] = len(pairs)

    return dataset_pairs, stats


class CombinedLOLDataset(Dataset):
    """
    Combined PyTorch Dataset for LOL-v1 and LOL-v2.
    Combines both datasets into a single training or testing split.
    """
    def __init__(self, data_root='data', split='train', paired_files=None,
                 crop_size=256, training=True, augment=True, transform=None):
        """
        Args:
            data_root (str): Root directory containing LOLv1 and LOLv2 subdirectories.
            split (str): 'train' or 'test'.
            paired_files (list of tuple): Optional pre-constructed list of (low_path, high_path).
            crop_size (int): Size of random square crop during training (e.g. 256).
            training (bool): Whether this is for training (enables crops/flips).
            augment (bool): Whether to apply random horizontal and vertical flips.
            transform (callable): Optional custom transform.
        """
        self.split = split
        self.crop_size = crop_size
        self.training = training
        self.augment = augment
        self.transform = transform

        if paired_files is not None:
            self.paired_files = paired_files
        else:
            all_pairs, stats = discover_lol_datasets(data_root)
            self.paired_files = all_pairs.get(split, [])
            self.stats = stats

        if len(self.paired_files) == 0:
            print(f"[Warning] No paired images found for split='{split}' under root='{data_root}'.")

    def __len__(self):
        return len(self.paired_files)

    def __getitem__(self, idx):
        low_path, high_path = self.paired_files[idx]

        low_image = Image.open(low_path).convert('RGB')
        high_image = Image.open(high_path).convert('RGB')

        if self.transform:
            low_image = self.transform(low_image)
            high_image = self.transform(high_image)

        # Training data augmentation: Random Crop and Flips
        if self.training and self.crop_size:
            w, h = low_image.size
            # Guard against images smaller than crop_size
            if w < self.crop_size or h < self.crop_size:
                pad_w = max(0, self.crop_size - w)
                pad_h = max(0, self.crop_size - h)
                low_image = TF.pad(low_image, (0, 0, pad_w, pad_h), padding_mode='reflect')
                high_image = TF.pad(high_image, (0, 0, pad_w, pad_h), padding_mode='reflect')
                w, h = low_image.size

            i, j, th, tw = transforms.RandomCrop.get_params(low_image, output_size=(self.crop_size, self.crop_size))
            low_image = TF.crop(low_image, i, j, th, tw)
            high_image = TF.crop(high_image, i, j, th, tw)

            if self.augment:
                if random.random() > 0.5:
                    low_image = TF.hflip(low_image)
                    high_image = TF.hflip(high_image)
                if random.random() > 0.5:
                    low_image = TF.vflip(low_image)
                    high_image = TF.vflip(high_image)

        # Convert to tensor [0, 1]
        low_tensor = TF.to_tensor(low_image)
        high_tensor = TF.to_tensor(high_image)

        # In testing mode, ensure dimensions are divisible by 8 for LYT-Net architecture
        if not self.training:
            c, h, w = low_tensor.shape
            pad_h = (8 - h % 8) % 8
            pad_w = (8 - w % 8) % 8
            if pad_h > 0 or pad_w > 0:
                low_tensor = torch.nn.functional.pad(low_tensor, (0, pad_w, 0, pad_h), mode='reflect')
                high_tensor = torch.nn.functional.pad(high_tensor, (0, pad_w, 0, pad_h), mode='reflect')

        return low_tensor, high_tensor


class PairedDataset(CombinedLOLDataset):
    """
    Backward-compatible PairedDataset class.
    Accepts low_dir and high_dir (strings or lists) or uses CombinedLOLDataset.
    """
    def __init__(self, low_dir=None, high_dir=None, transform=None, crop_size=None, training=True, augment=True):
        if low_dir is not None and high_dir is not None:
            if isinstance(low_dir, str) and isinstance(high_dir, str) and os.path.isdir(low_dir) and os.path.isdir(high_dir):
                pairs = find_paired_images_in_dirs(low_dir, high_dir)
            elif isinstance(low_dir, (list, tuple)) and isinstance(high_dir, (list, tuple)):
                pairs = []
                for ld, hd in zip(low_dir, high_dir):
                    pairs.extend(find_paired_images_in_dirs(ld, hd))
            else:
                pairs = []
            super().__init__(paired_files=pairs, crop_size=crop_size, training=training, augment=augment, transform=transform)
        else:
            super().__init__(crop_size=crop_size, training=training, augment=augment, transform=transform)


def create_dataloaders(train_low=None, train_high=None, test_low=None, test_high=None,
                       data_root='data', crop_size=256, batch_size=4, num_workers=None):
    """
    Creates train and test DataLoader instances combining LOL-v1 and LOL-v2 datasets.
    
    If explicit train_low / train_high are passed, uses those directories.
    Otherwise, automatically scans data_root for LOL-v1 and LOL-v2 combinations.
    """
    if num_workers is None:
        import sys
        num_workers = 0 if sys.platform == 'darwin' else 2
    train_loader = None
    test_loader = None

    if train_low and train_high:
        train_dataset = PairedDataset(train_low, train_high, crop_size=crop_size, training=True, augment=True)
    else:
        train_dataset = CombinedLOLDataset(data_root=data_root, split='train', crop_size=crop_size, training=True, augment=True)

    if len(train_dataset) > 0:
        train_loader = DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=num_workers,
            pin_memory=torch.cuda.is_available()
        )

    if test_low and test_high:
        test_dataset = PairedDataset(test_low, test_high, crop_size=None, training=False, augment=False)
    else:
        test_dataset = CombinedLOLDataset(data_root=data_root, split='test', crop_size=None, training=False, augment=False)

    if len(test_dataset) > 0:
        test_loader = DataLoader(
            test_dataset,
            batch_size=1,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=torch.cuda.is_available()
        )

    return train_loader, test_loader
