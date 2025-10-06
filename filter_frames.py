#! /usr/bin/env python3

import argparse
import csv
import json
import os
import random
import subprocess
import sys
from datetime import datetime

import av
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def plot_qp_over_time(data, output_dir="plots"):
    """Plot QP values over time"""
    timestamps = [float(row["ts"]) for row in data]
    qp_values = [int(row["qp"]) for row in data]
    frame_types = [row["type"] for row in data]

    # Convert timestamps to relative time (seconds from start)
    start_time = min(timestamps)
    relative_times = [
        (ts - start_time) / 1000000 for ts in timestamps
    ]  # Convert to seconds

    plt.figure(figsize=(12, 6))

    # Color code by frame type
    colors = {"key": "red", "delta": "blue"}
    for i, (time, qp, frame_type) in enumerate(
        zip(relative_times, qp_values, frame_types)
    ):
        plt.scatter(time, qp, c=colors.get(frame_type, "gray"), alpha=0.7, s=20)

    plt.xlabel("Time (seconds)")
    plt.ylabel("QP Value")
    plt.title("Quantization Parameter (QP) Over Time")
    plt.grid(True, alpha=0.3)

    # Add legend
    plt.scatter([], [], c="red", label="Key frames", alpha=0.7)
    plt.scatter([], [], c="blue", label="Delta frames", alpha=0.7)
    plt.legend()

    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/qp_over_time.png", dpi=300, bbox_inches="tight")
    plt.show()


def plot_frame_size_over_time(data, output_dir="plots"):
    """Plot frame size over time"""
    timestamps = [float(row["ts"]) for row in data]
    frame_sizes = [int(row["EncodedBufsz"]) for row in data]
    frame_types = [row["type"] for row in data]

    start_time = min(timestamps)
    relative_times = [(ts - start_time) / 1000000 for ts in timestamps]

    plt.figure(figsize=(12, 6))

    colors = {"key": "red", "delta": "blue"}
    for i, (time, size, frame_type) in enumerate(
        zip(relative_times, frame_sizes, frame_types)
    ):
        plt.scatter(time, size, c=colors.get(frame_type, "gray"), alpha=0.7, s=20)

    plt.xlabel("Time (seconds)")
    plt.ylabel("Frame Size (bytes)")
    plt.title("Frame Size Over Time")
    plt.grid(True, alpha=0.3)

    plt.scatter([], [], c="red", label="Key frames", alpha=0.7)
    plt.scatter([], [], c="blue", label="Delta frames", alpha=0.7)
    plt.legend()

    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/frame_size_over_time.png", dpi=300, bbox_inches="tight")
    plt.show()


def plot_packet_metrics(data, output_dir="plots"):
    """Plot packet-related metrics"""
    timestamps = [float(row["ts"]) for row in data]
    packets_expected = [int(row["NumPktExp"]) for row in data]
    packets_received = [int(row["NumPktRecv"]) for row in data]
    nacks = [int(row["NumNack"]) for row in data]

    start_time = min(timestamps)
    relative_times = [(ts - start_time) / 1000000 for ts in timestamps]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))

    # Packets expected vs received
    ax1.plot(relative_times, packets_expected, "b-", label="Expected", alpha=0.7)
    ax1.plot(relative_times, packets_received, "r-", label="Received", alpha=0.7)
    ax1.set_ylabel("Number of Packets")
    ax1.set_title("Packet Transmission Metrics")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # NACKs
    ax2.plot(relative_times, nacks, "orange", label="NACKs")
    ax2.set_ylabel("Number of NACKs")
    ax2.set_title("NACK Events Over Time")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # Packet loss rate
    loss_rates = [
        (exp - rec) / exp * 100 if exp > 0 else 0
        for exp, rec in zip(packets_expected, packets_received)
    ]
    ax3.plot(relative_times, loss_rates, "purple", label="Packet Loss Rate")
    ax3.set_xlabel("Time (seconds)")
    ax3.set_ylabel("Loss Rate (%)")
    ax3.set_title("Packet Loss Rate Over Time")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/packet_metrics.png", dpi=300, bbox_inches="tight")
    plt.show()


def plot_qp_distribution(data, output_dir="plots"):
    """Plot QP distribution by frame type"""
    key_frames = [int(row["qp"]) for row in data if row["type"] == "key"]
    delta_frames = [int(row["qp"]) for row in data if row["type"] == "delta"]

    plt.figure(figsize=(10, 6))

    plt.hist(
        [key_frames, delta_frames],
        bins=20,
        alpha=0.7,
        label=["Key frames", "Delta frames"],
        color=["red", "blue"],
    )

    plt.xlabel("QP Value")
    plt.ylabel("Frequency")
    plt.title("QP Distribution by Frame Type")
    plt.legend()
    plt.grid(True, alpha=0.3)

    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/qp_distribution.png", dpi=300, bbox_inches="tight")
    plt.show()


def calculate_bitrate(data):
    """Calculate instantaneous and average bitrate from frame data"""
    timestamps = [float(row["ts"]) for row in data]
    frame_sizes = [int(row["EncodedBufsz"]) for row in data]

    # Calculate time intervals between frames (in seconds)
    time_intervals = []
    for i in range(1, len(timestamps)):
        interval = (timestamps[i] - timestamps[i - 1]) / 1000000  # Convert to seconds
        time_intervals.append(interval)

    # Calculate instantaneous bitrates (bits per second)
    instantaneous_bitrates = []
    for i in range(1, len(frame_sizes)):
        if time_intervals[i - 1] > 0:
            bitrate = (frame_sizes[i] * 8) / time_intervals[
                i - 1
            ]  # Convert bytes to bits
            instantaneous_bitrates.append(bitrate)
        else:
            instantaneous_bitrates.append(0)

    # Calculate average bitrate
    total_bits = sum(frame_sizes) * 8
    total_time = (timestamps[-1] - timestamps[0]) / 1000000  # Total time in seconds
    average_bitrate = total_bits / total_time if total_time > 0 else 0

    return instantaneous_bitrates, average_bitrate, time_intervals


def plot_bitrate_over_time(data, output_dir="plots"):
    """Plot bitrate over time"""
    timestamps = [float(row["ts"]) for row in data]
    frame_sizes = [int(row["EncodedBufsz"]) for row in data]
    frame_types = [row["type"] for row in data]

    # Calculate bitrates
    instantaneous_bitrates, average_bitrate, time_intervals = calculate_bitrate(data)

    # Create time points for instantaneous bitrates (midpoints between frames)
    time_points = []
    for i in range(1, len(timestamps)):
        midpoint_time = (timestamps[i] + timestamps[i - 1]) / 2
        time_points.append(midpoint_time)

    # Convert to relative time
    start_time = min(timestamps)
    relative_times = [(t - start_time) / 1000000 for t in time_points]

    plt.figure(figsize=(12, 6))

    # Color code by frame type (use the second frame's type for each interval)
    colors = {"key": "red", "delta": "blue"}
    for i, (time, bitrate, frame_type) in enumerate(
        zip(relative_times, instantaneous_bitrates, frame_types[1:])
    ):
        plt.scatter(
            time, bitrate / 1000, c=colors.get(frame_type, "gray"), alpha=0.7, s=20
        )  # Convert to kbps

    # Add average bitrate line
    plt.axhline(
        y=average_bitrate / 1000,
        color="green",
        linestyle="--",
        label=f"Average: {average_bitrate/1000:.1f} kbps",
        linewidth=2,
    )

    plt.xlabel("Time (seconds)")
    plt.ylabel("Bitrate (kbps)")
    plt.title("Video Bitrate Over Time")
    plt.grid(True, alpha=0.3)

    # Add legend
    plt.scatter([], [], c="red", label="Key frames", alpha=0.7)
    plt.scatter([], [], c="blue", label="Delta frames", alpha=0.7)
    plt.legend()

    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/bitrate_over_time.png", dpi=300, bbox_inches="tight")
    plt.show()

    return average_bitrate


def filter_frames(data, criteria):
    """Filter frames based on specified criteria"""
    filtered_frames = []

    # Calculate bitrates for filtering
    instantaneous_bitrates, average_bitrate, time_intervals = calculate_bitrate(data)

    for i, frame in enumerate(data):
        include_frame = True

        # Check bitrate criteria
        if "bitrate_min" in criteria and i > 0:
            if (
                instantaneous_bitrates[i - 1] < criteria["bitrate_min"] * 1000
            ):  # Convert kbps to bps
                include_frame = False

        if "bitrate_max" in criteria and i > 0:
            if (
                instantaneous_bitrates[i - 1] > criteria["bitrate_max"] * 1000
            ):  # Convert kbps to bps
                include_frame = False

        # Check QP criteria
        if "qp_min" in criteria:
            if int(frame["qp"]) < criteria["qp_min"]:
                include_frame = False

        if "qp_max" in criteria:
            if int(frame["qp"]) > criteria["qp_max"]:
                include_frame = False

        # Check frame size criteria
        if "size_min" in criteria:
            if int(frame["EncodedBufsz"]) < criteria["size_min"]:
                include_frame = False

        if "size_max" in criteria:
            if int(frame["EncodedBufsz"]) > criteria["size_max"]:
                include_frame = False

        # Check frame type criteria
        if "frame_type" in criteria:
            if frame["type"] != criteria["frame_type"]:
                include_frame = False

        # Check packet loss criteria
        if "max_packet_loss" in criteria:
            packets_expected = int(frame["NumPktExp"])
            packets_received = int(frame["NumPktRecv"])
            if packets_expected > 0:
                loss_rate = (
                    (packets_expected - packets_received) / packets_expected * 100
                )
                if loss_rate > criteria["max_packet_loss"]:
                    include_frame = False

        # Check NACK criteria
        if "max_nacks" in criteria:
            if int(frame["NumNack"]) > criteria["max_nacks"]:
                include_frame = False

        if include_frame:
            filtered_frames.append(frame)

    return filtered_frames


def save_filtered_frames(filtered_frames, output_file):
    """Save filtered frame paths to a text file"""
    with open(output_file, "w") as f:
        for frame in filtered_frames:
            # Convert relative path to absolute path
            frame_path = Path(frame["File"]).resolve()
            f.write(f"{frame_path}\n")

    print(f"Saved {len(filtered_frames)} filtered frame paths to: {output_file}")


def print_filter_stats(original_data, filtered_data, criteria):
    """Print statistics about the filtering process"""
    print(f"\n=== FILTERING RESULTS ===")
    print(f"Original frames: {len(original_data)}")
    print(f"Filtered frames: {len(filtered_data)}")
    print(f"Filtered ratio: {len(filtered_data)/len(original_data)*100:.1f}%")

    print(f"\nApplied criteria:")
    for key, value in criteria.items():
        print(f"  {key}: {value}")

    if len(filtered_data) > 0:
        # Calculate bitrates for filtered frames
        filtered_bitrates, filtered_avg_bitrate, _ = calculate_bitrate(filtered_data)
        filtered_qp_values = [int(row["qp"]) for row in filtered_data]
        filtered_sizes = [int(row["EncodedBufsz"]) for row in filtered_data]

        print(f"\nFiltered frame statistics:")
        print(f"  Average bitrate: {filtered_avg_bitrate/1000:.1f} kbps")
        print(f"  QP range: {min(filtered_qp_values)} - {max(filtered_qp_values)}")
        print(f"  Size range: {min(filtered_sizes)} - {max(filtered_sizes)} bytes")


def print_summary_stats(data):
    """Print summary statistics"""
    qp_values = [int(row["qp"]) for row in data]
    frame_sizes = [int(row["EncodedBufsz"]) for row in data]
    packets_expected = [int(row["NumPktExp"]) for row in data]
    packets_received = [int(row["NumPktRecv"]) for row in data]

    key_frames = [row for row in data if row["type"] == "key"]
    delta_frames = [row for row in data if row["type"] == "delta"]

    # Calculate bitrate statistics
    instantaneous_bitrates, average_bitrate, time_intervals = calculate_bitrate(data)

    print("\n=== EXPERIMENT SUMMARY ===")
    print(f"Total frames: {len(data)}")
    print(f"Key frames: {len(key_frames)}")
    print(f"Delta frames: {len(delta_frames)}")
    print(f"Key frame ratio: {len(key_frames)/len(data)*100:.1f}%")

    print(f"\nQP Statistics:")
    print(f"  Min QP: {min(qp_values)}")
    print(f"  Max QP: {max(qp_values)}")
    print(f"  Mean QP: {np.mean(qp_values):.1f}")
    print(f"  Std QP: {np.std(qp_values):.1f}")

    print(f"\nFrame Size Statistics:")
    print(f"  Min size: {min(frame_sizes)} bytes")
    print(f"  Max size: {max(frame_sizes)} bytes")
    print(f"  Mean size: {np.mean(frame_sizes):.1f} bytes")

    print(f"\nBitrate Statistics:")
    print(f"  Average bitrate: {average_bitrate/1000:.1f} kbps")
    print(f"  Min instantaneous: {min(instantaneous_bitrates)/1000:.1f} kbps")
    print(f"  Max instantaneous: {max(instantaneous_bitrates)/1000:.1f} kbps")
    print(f"  Std instantaneous: {np.std(instantaneous_bitrates)/1000:.1f} kbps")

    total_expected = sum(packets_expected)
    total_received = sum(packets_received)
    loss_rate = (
        (total_expected - total_received) / total_expected * 100
        if total_expected > 0
        else 0
    )
    print(f"\nPacket Statistics:")
    print(f"  Total packets expected: {total_expected}")
    print(f"  Total packets received: {total_received}")
    print(f"  Overall loss rate: {loss_rate:.2f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and plot WebRTC experiment results"
    )
    parser.add_argument(
        "--processed_csv",
        "-i",
        type=str,
        required=True,
        help="Processed experiment results CSV file",
    )
    parser.add_argument(
        "--exp_config", "-c", type=str, required=True, help="Experiment config file"
    )

    parser.add_argument(
        "--plot_type",
        "-p",
        type=str,
        choices=["qp", "size", "packets", "distribution", "bitrate", "all"],
        default="all",
        help="Type of plot to generate",
    )
    parser.add_argument(
        "--output_dir",
        "-o",
        type=str,
        default="plots",
        help="Output directory for plots",
    )
    parser.add_argument(
        "--no_show", action="store_true", help="Don't display plots, only save them"
    )

    # Filtering arguments
    parser.add_argument("--filter", action="store_true", help="Enable frame filtering")
    parser.add_argument(
        "--filter_output", "-f", type=str, help="Output file for filtered frame paths"
    )

    # Bitrate filtering
    parser.add_argument("--bitrate_min", type=float, help="Minimum bitrate in kbps")
    parser.add_argument("--bitrate_max", type=float, help="Maximum bitrate in kbps")

    # QP filtering
    parser.add_argument("--qp_min", type=int, help="Minimum QP value")
    parser.add_argument("--qp_max", type=int, help="Maximum QP value")

    # Frame size filtering
    parser.add_argument("--size_min", type=int, help="Minimum frame size in bytes")
    parser.add_argument("--size_max", type=int, help="Maximum frame size in bytes")

    # Frame type filtering
    parser.add_argument(
        "--frame_type", type=str, choices=["key", "delta"], help="Filter by frame type"
    )

    # Network quality filtering
    parser.add_argument(
        "--max_packet_loss", type=float, help="Maximum packet loss rate (%)"
    )
    parser.add_argument("--max_nacks", type=int, help="Maximum number of NACKs")
    args = parser.parse_args()

    # Load experiment config
    with open(args.exp_config, "r") as exp_config_file:
        exp_config = json.load(exp_config_file)
        print(
            f"Experiment config: {exp_config['Width']}x{exp_config['Height']} @ {exp_config['Fps']}fps"
        )
        print(f"Duration: {exp_config['DurationMS']}ms")

    # Load and process CSV data
    with open(args.processed_csv, "r") as processed_csv_file:
        frames = list(csv.DictReader(processed_csv_file))

    print(f"Loaded {len(frames)} frames from {args.processed_csv}")

    # Handle filtering if requested
    if args.filter:
        # Build filtering criteria from command line arguments
        criteria = {}
        if args.bitrate_min is not None:
            criteria["bitrate_min"] = args.bitrate_min
        if args.bitrate_max is not None:
            criteria["bitrate_max"] = args.bitrate_max
        if args.qp_min is not None:
            criteria["qp_min"] = args.qp_min
        if args.qp_max is not None:
            criteria["qp_max"] = args.qp_max
        if args.size_min is not None:
            criteria["size_min"] = args.size_min
        if args.size_max is not None:
            criteria["size_max"] = args.size_max
        if args.frame_type is not None:
            criteria["frame_type"] = args.frame_type
        if args.max_packet_loss is not None:
            criteria["max_packet_loss"] = args.max_packet_loss
        if args.max_nacks is not None:
            criteria["max_nacks"] = args.max_nacks

        if not criteria:
            print("Warning: --filter specified but no filtering criteria provided!")
            print(
                "Available criteria: --bitrate_min, --bitrate_max, --qp_min, --qp_max, --size_min, --size_max, --frame_type, --max_packet_loss, --max_nacks"
            )
        else:
            # Apply filtering
            filtered_frames = filter_frames(frames, criteria)

            # Print filtering statistics
            print_filter_stats(frames, filtered_frames, criteria)

            # Save filtered frame paths if output file specified
            if args.filter_output:
                save_filtered_frames(filtered_frames, args.filter_output)
            else:
                print(
                    "Warning: No output file specified for filtered frames. Use --filter_output to save results."
                )

    # Print summary statistics
    print_summary_stats(frames)

    # Generate plots based on selection
    if args.no_show:
        plt.ioff()  # Turn off interactive mode

    if args.plot_type in ["qp", "all"]:
        print("\nGenerating QP over time plot...")
        plot_qp_over_time(frames, args.output_dir)

    if args.plot_type in ["size", "all"]:
        print("Generating frame size over time plot...")
        plot_frame_size_over_time(frames, args.output_dir)

    if args.plot_type in ["packets", "all"]:
        print("Generating packet metrics plot...")
        plot_packet_metrics(frames, args.output_dir)

    if args.plot_type in ["distribution", "all"]:
        print("Generating QP distribution plot...")
        plot_qp_distribution(frames, args.output_dir)

    if args.plot_type in ["bitrate", "all"]:
        print("Generating bitrate over time plot...")
        plot_bitrate_over_time(frames, args.output_dir)

    print(f"\nPlots saved to: {args.output_dir}/")


if __name__ == "__main__":
    exit(main())
