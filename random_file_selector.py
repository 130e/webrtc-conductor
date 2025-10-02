#!/usr/bin/env python3
import argparse
import random
import sys
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


def select_random_files(files, num_files, seed=None):
    """Randomly select a subset of files."""
    if seed is not None:
        random.seed(seed)

    if len(files) <= num_files:
        print(f"Warning: Only {len(files)} files available, selecting all.")
        return files

    return random.sample(files, num_files)


def save_selected_files(selected_files, output_file):
    """Save the selected files to the output file."""
    try:
        with open(output_file, "w") as f:
            for file_path in selected_files:
                f.write(file_path + "\n")
        print(f"Selected {len(selected_files)} files saved to '{output_file}'")
    except Exception as e:
        print(f"Error writing to file '{output_file}': {e}")
        sys.exit(1)


def print_statistics(files, selected_files, categories):
    """Print statistics about the selection."""
    print(f"\nSelection Statistics:")
    print(f"Total files available: {len(files)}")
    print(f"Files selected: {len(selected_files)}")

    if categories and "all" not in categories:
        print(f"Categories filtered: {', '.join(categories)}")

    # Count by category
    category_counts = {}
    for file_path in selected_files:
        if "/Celeb-real/" in file_path:
            category_counts["Celeb-real"] = category_counts.get("Celeb-real", 0) + 1
        elif "/Celeb-synthesis/" in file_path:
            category_counts["Celeb-synthesis"] = (
                category_counts.get("Celeb-synthesis", 0) + 1
            )
        elif "/YouTube-real/" in file_path:
            category_counts["YouTube-real"] = category_counts.get("YouTube-real", 0) + 1

    print(f"\nSelection breakdown by category:")
    for category, count in sorted(category_counts.items()):
        print(f"  {category}: {count} files")


def main():
    parser = argparse.ArgumentParser(
        description="Randomly select a subset of files from the dataset",
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
        "--output-file",
        "-o",
        default="random_selected_test.txt",
        help="Output file to save selected files (default: random_selected_test.txt)",
    )

    parser.add_argument(
        "--num-files",
        "-n",
        type=int,
        default=10,
        help="Number of files to select (default: 10)",
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

    print(f"Randomly selecting {args.num_files} files (seed: {args.seed})")
    selected_files = select_random_files(filtered_files, args.num_files, args.seed)

    save_selected_files(selected_files, args.output_file)
    print_statistics(files, selected_files, categories)

    print(f"\nSelected files preview (first 10):")
    for i, file_path in enumerate(selected_files[:10]):
        print(f"  {i+1:2d}. {file_path}")

    if len(selected_files) > 10:
        print(f"  ... and {len(selected_files) - 10} more files")


if __name__ == "__main__":
    main()
