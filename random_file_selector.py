#!/usr/bin/env python3
"""
Random Batch Splitter for Video Dataset
======================================

This script randomly splits files from the input file into batches of specified size.
This is useful for running experiments in manageable batches instead of processing
all files at once.

Usage:
    python random_file_selector.py [options]

Options:
    --input-file: Input file path (required)
    --batch-size: Number of files per batch (default: 10)
    --output-prefix: Prefix for output batch files (default: batch_)
    --seed: Random seed for reproducibility (default: 42)
    --categories: Comma-separated list of categories to include (default: all)
                  Available categories: Celeb-real, Celeb-synthesis, YouTube-real
"""

import argparse
import random
import sys
import math
from pathlib import Path


def read_file_list(input_file):
    """Read the list of files from the input file."""
    try:
        with open(input_file, "r") as f:
            files = [line.strip() for line in f if line.strip()]
        return files
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{input_file}': {e}")
        sys.exit(1)


def filter_by_categories(files, categories):
    """Filter files by specified categories."""
    if not categories or "all" in categories:
        return files

    filtered_files = []
    for file_path in files:
        for category in categories:
            if f"/{category}/" in file_path:
                filtered_files.append(file_path)
                break

    return filtered_files


def shuffle_files(files, seed=None):
    """Randomly shuffle the list of files."""
    if seed is not None:
        random.seed(seed)
    
    shuffled_files = files.copy()
    random.shuffle(shuffled_files)
    return shuffled_files


def split_into_batches(files, batch_size):
    """Split files into batches of specified size."""
    batches = []
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        batches.append(batch)
    return batches


def save_batches(batches, output_prefix, output_dir):
    """Save batches to separate files in the specified directory."""
    batch_files = []
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        for i, batch in enumerate(batches):
            batch_file = Path(output_dir) / f"{output_prefix}{i+1:03d}.txt"
            with open(batch_file, "w") as f:
                for file_path in batch:
                    f.write(file_path + "\n")
            batch_files.append(str(batch_file))
            print(f"Batch {i+1}: {len(batch)} files saved to '{batch_file}'")
        return batch_files
    except Exception as e:
        print(f"Error writing batch files: {e}")
        sys.exit(1)


def print_batch_statistics(files, batches, categories):
    """Print statistics about the batch splitting."""
    total_files = sum(len(batch) for batch in batches)
    print(f"\nBatch Statistics:")
    print(f"Total files available: {len(files)}")
    print(f"Files distributed: {total_files}")
    print(f"Number of batches: {len(batches)}")
    print(f"Average files per batch: {total_files / len(batches):.1f}")

    if categories and "all" not in categories:
        print(f"Categories filtered: {', '.join(categories)}")

    # Count by category across all batches
    category_counts = {}
    for batch in batches:
        for file_path in batch:
            if "/Celeb-real/" in file_path:
                category_counts["Celeb-real"] = category_counts.get("Celeb-real", 0) + 1
            elif "/Celeb-synthesis/" in file_path:
                category_counts["Celeb-synthesis"] = (
                    category_counts.get("Celeb-synthesis", 0) + 1
                )
            elif "/YouTube-real/" in file_path:
                category_counts["YouTube-real"] = category_counts.get("YouTube-real", 0) + 1

    print(f"\nDistribution breakdown by category:")
    for category, count in sorted(category_counts.items()):
        print(f"  {category}: {count} files")

    print(f"\nBatch sizes:")
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}: {len(batch)} files")


def main():
    parser = argparse.ArgumentParser(
        description="Randomly split files into batches for processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--input-file",
        "-i",
        help="Input file containing the list of files",
        required=True,
    )

    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=10,
        help="Number of files per batch (default: 10)",
    )

    parser.add_argument(
        "--output-prefix",
        "-o",
        default="batch_",
        help="Prefix for output batch files (default: batch_)",
    )

    parser.add_argument(
        "--output-dir",
        "-d",
        default=".",
        help="Output directory for batch files (default: current directory)",
    )

    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )

    parser.add_argument(
        "--categories",
        "-c",
        default="all",
        help="Comma-separated list of categories to include (default: all). ",
    )

    args = parser.parse_args()

    # Parse categories
    if args.categories.lower() == "all":
        categories = None
    else:
        categories = [cat.strip() for cat in args.categories.split(",")]
        # TODO: Currently hard-coded categories
        valid_categories = {"Celeb-real", "Celeb-synthesis", "YouTube-real"}
        invalid_categories = set(categories) - valid_categories
        if invalid_categories:
            print(f"Error: Invalid categories: {invalid_categories}")
            print(f"Valid categories: {', '.join(valid_categories)}")
            sys.exit(1)

    print(f"Reading files from: {args.input_file}")
    files = read_file_list(args.input_file)

    print(f"Filtering by categories: {categories if categories else 'all'}")
    filtered_files = filter_by_categories(files, categories)

    if not filtered_files:
        print("Error: No files found matching the specified categories.")
        sys.exit(1)

    print(f"Randomly shuffling {len(filtered_files)} files (seed: {args.seed})")
    shuffled_files = shuffle_files(filtered_files, args.seed)

    print(f"Splitting into batches of size {args.batch_size}")
    batches = split_into_batches(shuffled_files, args.batch_size)

    batch_files = save_batches(batches, args.output_prefix, args.output_dir)
    print_batch_statistics(files, batches, categories)

    print(f"\nBatch files created:")
    for batch_file in batch_files:
        print(f"  {batch_file}")

    print(f"\nFirst batch preview (batch_001.txt):")
    if batches:
        for i, file_path in enumerate(batches[0][:5]):
            print(f"  {i+1:2d}. {file_path}")
        if len(batches[0]) > 5:
            print(f"  ... and {len(batches[0]) - 5} more files in this batch")


if __name__ == "__main__":
    main()
