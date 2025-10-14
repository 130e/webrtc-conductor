#! /usr/bin/env python3

import argparse
import code
import os
import sys
import csv
import json
import numpy as np
import matplotlib.pyplot as plt
import yaml


def load_frame_data(frame_summary_path):
    """Load frame data from CSV file including timestamps, resolutions, sizes, QP values, and bitrate."""
    frame_data_csv = {}
    if os.path.exists(frame_summary_path):
        with open(frame_summary_path, "r") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    frame_index = int(row["frame_index"])
                    timestamp = float(row["video_RelativeTime"])
                    width = int(row["video_width"])
                    height = int(row["video_height"])
                    size = int(row["video_size"])
                    log_qp = float(row["log_qp"])
                    log_assembled_numpktexp = float(row["log_Assembled_NumPktExp"])
                    log_assembled_numnack = float(row["log_Assembled_NumNack"])
                    frame_data_csv[frame_index] = {
                        "timestamp": timestamp,
                        "width": width,
                        "height": height,
                        "resolution": f"{width}x{height}",
                        "size": size,
                        "log_qp": log_qp,
                        "log_assembled_numpktexp": log_assembled_numpktexp,
                        "log_assembled_numnack": log_assembled_numnack,
                    }
                except (ValueError, KeyError):
                    continue

    # Calculate bitrate using sliding window for all frames
    if frame_data_csv:
        # Sort frames by timestamp first
        sorted_frames = sorted(frame_data_csv.items(), key=lambda x: x[1]["timestamp"])

        # Sliding window parameters
        window_duration = 1.0  # 1 second window
        min_frames_in_window = 2  # minimum frames needed for bitrate calculation

        for i, (frame_id, frame_data) in enumerate(sorted_frames):
            # Find frames within the time window
            current_time = frame_data["timestamp"]
            window_start_time = current_time - window_duration

            # Collect frames in the window
            window_frames = []
            for j in range(max(0, i - 100), i + 1):  # Look back up to 100 frames
                j_frame_id, j_frame_data = sorted_frames[j]
                if j_frame_data["timestamp"] >= window_start_time:
                    window_frames.append((j_frame_id, j_frame_data))

            # Calculate bitrate if we have enough frames
            if len(window_frames) >= min_frames_in_window:
                # Calculate total bytes in window
                total_bytes = sum(frame_data["size"] for _, frame_data in window_frames)

                # Calculate time span of window
                time_span = (
                    window_frames[-1][1]["timestamp"] - window_frames[0][1]["timestamp"]
                )

                # Calculate bitrate (bits per second)
                if time_span > 0:
                    bitrate_bps = (total_bytes * 8) / time_span  # Convert bytes to bits
                    bitrate_kbps = bitrate_bps / 1000  # Convert to kbps
                    frame_data_csv[frame_id]["bitrate"] = bitrate_kbps
                else:
                    frame_data_csv[frame_id]["bitrate"] = 0
            else:
                frame_data_csv[frame_id]["bitrate"] = 0

    return frame_data_csv


def correlate_frame_data(frames_data, frame_data_csv):
    """Correlate detector predictions with frame data.

    Args:
        frames_data: Detector prediction data for frames
        frame_data_csv: Frame metadata (timestamps, resolutions, sizes, QP, NACK, bitrate)

    Returns:
        Dictionary of frame predictions with correlated data, or None if no data
    """
    frame_predictions = {}
    for frame_id, frame_data in frames_data.items():
        if "pred" in frame_data:
            try:
                frame_num = int(frame_id)
                if frame_num in frame_data_csv:
                    csv_data = frame_data_csv[frame_num]
                    frame_predictions[frame_num] = {
                        "pred": frame_data["pred"],
                        "timestamp": csv_data["timestamp"],
                        "width": csv_data["width"],
                        "height": csv_data["height"],
                        "resolution": csv_data["resolution"],
                        "size": csv_data["size"],
                        "qp": csv_data["log_qp"],
                        "assembled_numpktexp": csv_data["log_assembled_numpktexp"],
                        "assembled_numnack": csv_data["log_assembled_numnack"],
                        "bitrate": csv_data["bitrate"],
                    }
            except ValueError:
                continue

    # Sort frames by timestamp for consistent ordering
    sorted_frames = sorted(frame_predictions.items(), key=lambda x: x[1]["timestamp"])

    return frame_predictions, sorted_frames


# TODO: Celeb-DF only
def infer_video_cfg(video_id, config):
    if config["dataset_name"] == "Celeb-DF-v1":
        stripped_video_id = os.path.basename(
            video_id.replace(config["video_suffix"], "")
        )
        if "Celeb-synthesis" in video_id:
            return "fake", stripped_video_id
        else:
            return "real", stripped_video_id
    else:
        return "", ""


def plot_video_metrics(frames, figure_title, figure_path, metrics):
    def plot_metric(ax, metric, frames, colors):
        start_idx = 0
        cur_idx = 0
        prev_resolution = frames[0][1]["resolution"]
        while cur_idx < len(frames):
            resolution = frames[cur_idx][1]["resolution"]
            if resolution != prev_resolution:
                # Segment ends; plot
                timestamps = [
                    frm["timestamp"] for frm_id, frm in frames[start_idx:cur_idx]
                ]
                predictions = [frm[metric] for frm_id, frm in frames[start_idx:cur_idx]]
                ax.plot(
                    timestamps,
                    predictions,
                    color=colors[prev_resolution],
                    linewidth=2,
                    marker="o",
                    markersize=3,
                    alpha=0.9,
                    label=prev_resolution,
                )
                start_idx = cur_idx
                prev_resolution = resolution
            cur_idx += 1
        # Plot last segment
        timestamps = [frm["timestamp"] for frm_id, frm in frames[start_idx:cur_idx]]
        predictions = [frm[metric] for frm_id, frm in frames[start_idx:cur_idx]]
        ax.plot(
            timestamps,
            predictions,
            color=colors[prev_resolution],
            linewidth=2,
            marker="o",
            markersize=3,
            alpha=0.9,
            label=prev_resolution,
        )
        if metric == "pred":
            ax.axhline(y=0.5, color="red", linestyle="--", alpha=0.7, linewidth=1.5)
            ax.legend(loc="upper right", title="Resolution")

    # split by resolutions
    resolutions = set()
    for frame_index, frame_data in frames:
        resolutions.add(frame_data["resolution"])

    colors = dict(zip(resolutions, plt.cm.tab10(range(len(resolutions)))))

    num_plots = len(metrics)
    fig, axes = plt.subplots(num_plots, 1, figsize=(12, 3 * num_plots), sharex=True)
    if num_plots == 1:
        axes = [axes]

    # Plot main figure
    ax = axes[0]
    metric = metrics[0]
    plot_metric(ax, metric, frames, colors)
    ax.set_title(figure_title)
    ax.set_ylabel(metric)

    for i in range(1, num_plots):
        ax = axes[i]
        plot_metric(ax, metrics[i], frames, colors)
        ax.set_ylabel(metrics[i])
    axes[-1].set_xlabel("Time (s)")

    plt.savefig(figure_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Plot saved as: {figure_path}")


def main():
    """Main function to process video data and generate visualization plots."""
    parser = argparse.ArgumentParser(description="Generate RTC input")
    parser.add_argument(
        "--config", "-c", type=str, required=True, help="Path to config file"
    )
    args = parser.parse_args()

    # Load configuration
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    with open(config["visualize_list"], "r") as f:
        video_lists = [line.strip() for line in f]

    # TODO
    metrics = ["pred", "bitrate", "qp"]

    video_cfg = {}
    for video_id in video_lists:
        label, stripped_id = infer_video_cfg(video_id, config)
        video_cfg[stripped_id] = {"label": label, "video_id": video_id}

    previous_threshold = 0
    bitrate_thresholds = []
    for threshold in config["bitrate_thresholds"]:
        bitrate_thresholds.append((previous_threshold, threshold))
        previous_threshold = threshold
    bitrate_thresholds.append((previous_threshold, float("inf")))

    print(f"Bitrate thresholds: {bitrate_thresholds}")
    figure_dir = os.path.join(
        config["figure_dir"], config["experiment_id"], config["detector"]
    )
    os.makedirs(figure_dir, exist_ok=True)

    detector_result = os.path.join(
        config["detector_input_dir"], config["experiment_id"], config["detector_result"]
    )

    with open(detector_result, "r") as f:
        detector_data = json.load(f)

    if config["dataset_name"] in detector_data:
        dataset_data = detector_data[config["dataset_name"]]
        if "video" in dataset_data:
            for stripped_id, frames_data in dataset_data["video"].items():
                video_id = video_cfg[stripped_id]["video_id"]
                print(f"Processing {video_id}")
                frame_summary_path = os.path.join(
                    config["processed_rtc_dir"],
                    config["dataset_name"],
                    video_id.replace(config["video_suffix"], ".csv"),
                )
                frame_data_csv = load_frame_data(frame_summary_path)
                if not frame_data_csv:
                    print(
                        f"Warning: Frame summary file not found or empty: {frame_summary_path}"
                    )
                    continue
                frame_predictions, sorted_frames = correlate_frame_data(
                    frames_data, frame_data_csv
                )

                figure_title = f"{video_cfg[stripped_id]['label']}-{stripped_id}-{config['detector']}"
                idx = 0
                prev_timestamp = sorted_frames[idx][1]["timestamp"]
                start_idx = idx
                while idx < len(sorted_frames):
                    if (
                        sorted_frames[idx][1]["timestamp"] - prev_timestamp
                        > config["plot_interval"]
                    ):
                        timestamp = round(prev_timestamp)
                        figure_path = os.path.join(
                            figure_dir, f"{figure_title}-{timestamp}.png"
                        )
                        plot_video_metrics(
                            sorted_frames[start_idx:idx],
                            f"{figure_title}-{timestamp}",
                            figure_path,
                            metrics,
                        )
                        prev_timestamp = sorted_frames[idx][1]["timestamp"]
                        start_idx = idx
                    idx += 1

                # Plot
                figure_title = f"{video_cfg[stripped_id]['label']}-{stripped_id}-{config['detector']}"
                figure_path = os.path.join(figure_dir, f"{figure_title}.png")
                plot_video_metrics(sorted_frames, figure_title, figure_path, metrics)

    else:
        print(
            f"No video data found in the detector results for {config['dataset_name']}"
        )


if __name__ == "__main__":
    main()
