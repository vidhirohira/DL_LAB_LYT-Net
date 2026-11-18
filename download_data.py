import os
import sys
import shutil
import zipfile
import tarfile
import argparse

try:
    import gdown
except ImportError:
    print("Installing missing 'gdown' package...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])
    import gdown

# Google Drive IDs from README
LOLV1_DRIVE_ID = "1vhJg75hIpYvsmryyaxdygAWeHuiY_HWu"
LOLV2_DRIVE_ID = "1OMfP6Ks2QKJcru1wS2eP629PgvKqF2Tw"

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.PNG', '.JPG')


def extract_archive(archive_path, extract_to):
    """Extracts zip, tar, tar.gz, or tgz archive to extract_to directory."""
    print(f"Extracting '{archive_path}' to '{extract_to}'...")
    os.makedirs(extract_to, exist_ok=True)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as z:
            z.extractall(extract_to)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, 'r:*') as t:
            t.extractall(extract_to)
    else:
        # Fallback to shutil
        shutil.unpack_archive(archive_path, extract_to)
    print("Extraction complete.")


def find_dirs_matching(root, target_patterns):
    """Searches recursively for directories whose path matches any of target_patterns."""
    matches = []
    for dirpath, dirnames, _ in os.walk(root):
        norm_path = dirpath.replace('\\', '/')
        for pattern in target_patterns:
            if pattern.lower() in norm_path.lower():
                matches.append(dirpath)
                break
    return matches


def copy_or_move_images(src_dir, dst_dir):
    """Copies all image files from src_dir into dst_dir."""
    if not os.path.isdir(src_dir):
        return 0
    os.makedirs(dst_dir, exist_ok=True)
    copied = 0
    for f in sorted(os.listdir(src_dir)):
        if f.endswith(IMAGE_EXTENSIONS) and not f.startswith('.'):
            src_file = os.path.join(src_dir, f)
            dst_file = os.path.join(dst_dir, f)
            if not os.path.exists(dst_file) or os.path.getsize(dst_file) != os.path.getsize(src_file):
                shutil.copy2(src_file, dst_file)
            copied += 1
    return copied


def organize_lolv1(extracted_root, target_root):
    """
    Organizes LOL-v1 into:
      target_root/LOLv1/Train/input
      target_root/LOLv1/Train/target
      target_root/LOLv1/Test/input
      target_root/LOLv1/Test/target
    """
    print("\n--- Organizing LOL-v1 ---")
    lolv1_dest = os.path.join(target_root, "LOLv1")
    train_in_dst = os.path.join(lolv1_dest, "Train", "input")
    train_gt_dst = os.path.join(lolv1_dest, "Train", "target")
    test_in_dst = os.path.join(lolv1_dest, "Test", "input")
    test_gt_dst = os.path.join(lolv1_dest, "Test", "target")

    # Search for our485 (train) and eval15 (test) or Train / Test
    train_low_src = None
    train_high_src = None
    test_low_src = None
    test_high_src = None

    for dirpath, dirnames, filenames in os.walk(extracted_root):
        norm = dirpath.replace('\\', '/').lower()
        # Train low candidates
        if ('our485/low' in norm or 'train/low' in norm or 'train/input' in norm) and train_low_src is None:
            train_low_src = dirpath
        # Train high candidates
        if ('our485/high' in norm or 'train/high' in norm or 'train/target' in norm or 'train/normal' in norm) and train_high_src is None:
            train_high_src = dirpath
        # Test low candidates
        if ('eval15/low' in norm or 'test/low' in norm or 'test/input' in norm) and test_low_src is None:
            test_low_src = dirpath
        # Test high candidates
        if ('eval15/high' in norm or 'test/high' in norm or 'test/target' in norm or 'test/normal' in norm) and test_high_src is None:
            test_high_src = dirpath

    # If already in LOLv1/Train/input structure inside extracted_root
    if not train_low_src:
        candidates = find_dirs_matching(extracted_root, ['train/input', 'train/low', 'our485/low'])
        if candidates:
            train_low_src = candidates[0]
    if not train_high_src:
        candidates = find_dirs_matching(extracted_root, ['train/target', 'train/high', 'train/normal', 'our485/high'])
        if candidates:
            train_high_src = candidates[0]
    if not test_low_src:
        candidates = find_dirs_matching(extracted_root, ['test/input', 'test/low', 'eval15/low'])
        if candidates:
            test_low_src = candidates[0]
    if not test_high_src:
        candidates = find_dirs_matching(extracted_root, ['test/target', 'test/high', 'test/normal', 'eval15/high'])
        if candidates:
            test_high_src = candidates[0]

    c_train_in = copy_or_move_images(train_low_src, train_in_dst) if train_low_src else 0
    c_train_gt = copy_or_move_images(train_high_src, train_gt_dst) if train_high_src else 0
    c_test_in = copy_or_move_images(test_low_src, test_in_dst) if test_low_src else 0
    c_test_gt = copy_or_move_images(test_high_src, test_gt_dst) if test_high_src else 0

    print(f"LOL-v1 Organization Result:")
    print(f"  Train: {c_train_in} input, {c_train_gt} target images -> '{train_in_dst}', '{train_gt_dst}'")
    print(f"  Test : {c_test_in} input, {c_test_gt} target images -> '{test_in_dst}', '{test_gt_dst}'")


def organize_lolv2(extracted_root, target_root):
    """
    Organizes LOL-v2 into:
      target_root/LOLv2/Real_captured/Train/Low & Normal
      target_root/LOLv2/Real_captured/Test/Low & Normal
      target_root/LOLv2/Synthetic/Train/Low & Normal
      target_root/LOLv2/Synthetic/Test/Low & Normal
    """
    print("\n--- Organizing LOL-v2 ---")
    lolv2_dest = os.path.join(target_root, "LOLv2")

    # Mapping of target paths
    targets = {
        'real_train_low': os.path.join(lolv2_dest, "Real_captured", "Train", "Low"),
        'real_train_high': os.path.join(lolv2_dest, "Real_captured", "Train", "Normal"),
        'real_test_low': os.path.join(lolv2_dest, "Real_captured", "Test", "Low"),
        'real_test_high': os.path.join(lolv2_dest, "Real_captured", "Test", "Normal"),
        'syn_train_low': os.path.join(lolv2_dest, "Synthetic", "Train", "Low"),
        'syn_train_high': os.path.join(lolv2_dest, "Synthetic", "Train", "Normal"),
        'syn_test_low': os.path.join(lolv2_dest, "Synthetic", "Test", "Low"),
        'syn_test_high': os.path.join(lolv2_dest, "Synthetic", "Test", "Normal")
    }

    # Search across extracted_root
    sources = {}
    for dirpath, dirnames, filenames in os.walk(extracted_root):
        norm = dirpath.replace('\\', '/').lower()
        # Real_captured
        if 'real' in norm:
            if 'train' in norm:
                if 'low' in norm or 'input' in norm:
                    sources['real_train_low'] = dirpath
                elif 'normal' in norm or 'high' in norm or 'target' in norm:
                    sources['real_train_high'] = dirpath
            elif 'test' in norm:
                if 'low' in norm or 'input' in norm:
                    sources['real_test_low'] = dirpath
                elif 'normal' in norm or 'high' in norm or 'target' in norm:
                    sources['real_test_high'] = dirpath
        # Synthetic
        elif 'syn' in norm:
            if 'train' in norm:
                if 'low' in norm or 'input' in norm:
                    sources['syn_train_low'] = dirpath
                elif 'normal' in norm or 'high' in norm or 'target' in norm:
                    sources['syn_train_high'] = dirpath
            elif 'test' in norm:
                if 'low' in norm or 'input' in norm:
                    sources['syn_test_low'] = dirpath
                elif 'normal' in norm or 'high' in norm or 'target' in norm:
                    sources['syn_test_high'] = dirpath

    # If LOLv2 has direct Train/Low, Train/Normal without Real_captured wrapper
    if 'real_train_low' not in sources:
        for dirpath, dirnames, filenames in os.walk(extracted_root):
            norm = dirpath.replace('\\', '/').lower()
            if 'train/low' in norm:
                sources['real_train_low'] = dirpath
            elif 'train/normal' in norm:
                sources['real_train_high'] = dirpath
            elif 'test/low' in norm:
                sources['real_test_low'] = dirpath
            elif 'test/normal' in norm:
                sources['real_test_high'] = dirpath

    for key, dst in targets.items():
        src = sources.get(key)
        count = copy_or_move_images(src, dst) if src else 0
        if count > 0:
            print(f"  {key:15s}: {count:4d} images copied to '{dst}'")


def main():
    parser = argparse.ArgumentParser(description="Download and organize LOL-v1 and LOL-v2 datasets.")
    parser.add_argument('--data_dir', type=str, default='data', help="Output data directory (default: 'data')")
    parser.add_argument('--downloads_dir', type=str, default='data/downloads', help="Temporary downloads directory")
    parser.add_argument('--skip_download', action='store_true', help="Skip download if archives are already placed")
    args = parser.parse_args()

    os.makedirs(args.data_dir, exist_ok=True)
    os.makedirs(args.downloads_dir, exist_ok=True)

    print("==================================================")
    print("      LOL-v1 & LOL-v2 Dataset Preparation         ")
    print("==================================================")
    print(f"Destination Root : {os.path.abspath(args.data_dir)}")
    print(f"Downloads Cache  : {os.path.abspath(args.downloads_dir)}")
    print("==================================================")

    # Move existing test_lolv1.zip if present
    if os.path.isfile("test_lolv1.zip") and not os.path.exists(os.path.join(args.downloads_dir, "lolv1.zip")):
        shutil.move("test_lolv1.zip", os.path.join(args.downloads_dir, "lolv1.zip"))

    lolv1_archive = os.path.join(args.downloads_dir, "lolv1.zip")
    lolv2_archive = os.path.join(args.downloads_dir, "lolv2.zip")

    # 1. Download LOL-v1
    if not os.path.isfile(lolv1_archive) or os.path.getsize(lolv1_archive) < 1000000:
        print("\n[1/4] Downloading LOL-v1 archive from Google Drive...")
        gdown.download(id=LOLV1_DRIVE_ID, output=lolv1_archive, quiet=False)
    else:
        print(f"\n[1/4] LOL-v1 archive already exists ({os.path.getsize(lolv1_archive) / (1024*1024):.1f} MB). Skipping download.")

    # 2. Download LOL-v2
    # Check if any lolv2 archive exists (zip or tar)
    existing_lolv2 = None
    for f in os.listdir(args.downloads_dir):
        if 'lolv2' in f.lower() and os.path.getsize(os.path.join(args.downloads_dir, f)) > 1000000:
            existing_lolv2 = os.path.join(args.downloads_dir, f)
            break

    if existing_lolv2:
        lolv2_archive = existing_lolv2
        print(f"\n[2/4] LOL-v2 archive already exists ({os.path.getsize(lolv2_archive) / (1024*1024):.1f} MB). Skipping download.")
    else:
        print("\n[2/4] Downloading LOL-v2 archive from Google Drive...")
        downloaded = gdown.download(id=LOLV2_DRIVE_ID, output=lolv2_archive, quiet=False)
        if downloaded is None or not os.path.isfile(lolv2_archive):
            # Try downloading into downloads_dir keeping Google Drive filename
            gdown.download(id=LOLV2_DRIVE_ID, output=args.downloads_dir + "/", quiet=False)
            for f in os.listdir(args.downloads_dir):
                if 'lol' in f.lower() and f != os.path.basename(lolv1_archive):
                    lolv2_archive = os.path.join(args.downloads_dir, f)
                    break

    # 3. Extract and organize LOL-v1
    print("\n[3/4] Extracting and organizing LOL-v1...")
    extract_tmp_v1 = os.path.join(args.downloads_dir, "extracted_v1")
    extract_archive(lolv1_archive, extract_tmp_v1)
    organize_lolv1(extract_tmp_v1, args.data_dir)

    # 4. Extract and organize LOL-v2
    print("\n[4/4] Extracting and organizing LOL-v2...")
    extract_tmp_v2 = os.path.join(args.downloads_dir, "extracted_v2")
    extract_archive(lolv2_archive, extract_tmp_v2)
    organize_lolv2(extract_tmp_v2, args.data_dir)

    # 5. Verification using dataloader discovery
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "PyTorch"))
    from dataloader import discover_lol_datasets
    dataset_pairs, stats = discover_lol_datasets(args.data_dir)

    print("\n==================================================")
    print("             Dataset Verification                 ")
    print("==================================================")
    print(f"Data Root               : {stats['root']}")
    print(f"  - LOL-v1 Train        : {stats['LOLv1_train']:4d} pairs | Test: {stats['LOLv1_test']:4d} pairs")
    print(f"  - LOL-v2 Real Train   : {stats['LOLv2_Real_train']:4d} pairs | Test: {stats['LOLv2_Real_test']:4d} pairs")
    print(f"  - LOL-v2 Syn Train    : {stats['LOLv2_Synthetic_train']:4d} pairs | Test: {stats['LOLv2_Synthetic_test']:4d} pairs")
    print("--------------------------------------------------")
    total_train = len(dataset_pairs['train'])
    total_test = len(dataset_pairs['test'])
    total_all = total_train + total_test
    print(f"Total Combined Train Pairs : {total_train:4d}")
    print(f"Total Combined Test Pairs  : {total_test:4d}")
    print(f"Total Combined Images      : {total_all:4d}")
    print("==================================================")

    if total_all >= 500:
        print("Dataset preparation and verification SUCCESSFUL!")
    else:
        print("[Warning] Total image count is less than expected. Please inspect extracted folders.")


if __name__ == '__main__':
    main()
