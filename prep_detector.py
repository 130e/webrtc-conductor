#!/usr/bin/env python3

import argparse
import os
import sys
import csv
import subprocess
from pathlib import Path
import av
from typing import List, Tuple, Dict, Any
import yaml
import json


def encode_video(
    input_video: str, output_video: str, width: int, height: int, fps: int = 30
) -> bool:
    """Encode entire video using ffmpeg with highest resolution"""
    try:
        # Adjust dimensions to be H.264 compatible (width multiple of 16, height multiple of 2)
        adjusted_width = ((width + 15) // 16) * 16
        adjusted_height = ((height + 1) // 2) * 2

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_video), exist_ok=True)

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-i",
            input_video,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-s",
            f"{adjusted_width}x{adjusted_height}",
            "-r",
            str(fps),
            "-y",  # Overwrite output file
            output_video,
        ]

        # Run ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"{output_video}")
            return True
        else:
            print(f"✗ ffmpeg error: {result.stderr}")
            return False

    except Exception as e:
        print(f"✗ Error running ffmpeg: {e}")
        return False


def generate_detector_input(config: Dict):
    with open(config["detect_list"], "r") as f:
        video_lists = [line.strip() for line in f]

    if config["dataset_name"] == "Celeb-DF-v1":
        list_file_path = os.path.join(
            config["detector_input_dir"],
            config["experiment_id"],
            config["dataset_name"],
            "List_of_testing_videos.txt",
        )
        with open(list_file_path, "w") as f:
            for video_id in video_lists:
                label = 0 if "Celeb-synthesis" in video_id else 1
                f.write(f"{label} {video_id}\n")
        print(f"Generated detector input list: {list_file_path}")
        print(f"Added {len(video_lists)} videos to the list")
        return list_file_path
    else:
        print("unsupported dataset yet")
        return None


def create_deepfakebench_symlinks(config: Dict):
    def create_symlink(src, link):
        if os.path.islink(link):
            print(f"Removing existing symlink '{link}'...")
            os.remove(link)
        elif os.path.isdir(link):
            print(
                f"Warning: '{link}' is a real directory. Skipping removal for safety."
            )
            return

        print(f"Creating symlink: {link} -> {src}")
        os.symlink(src, link)

    src = os.path.join(config["detector_input_dir"], config["experiment_id"])
    src = os.path.abspath(src)
    create_symlink(src, config["detector_preprocessing_dir"])
    create_symlink(src, config["detector_eval_dest_dir"])


def main():
    parser = argparse.ArgumentParser(description="Format received video for detector")
    parser.add_argument(
        "--config", "-c", type=str, required=True, help="Path to config file"
    )
    args = parser.parse_args()

    # Load configuration
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    with open(config["detect_list"], "r") as f:
        video_lists = [line.strip() for line in f]

    detector_input_videos = []

    for video_id in video_lists:
        print(f"Processing {video_id}")

        input_video_config_path = os.path.join(
            config["rtc_input_dir"],
            config["dataset_name"],
            video_id.replace(config["video_suffix"], ".json"),
        )

        rtc_output_video = os.path.join(
            config["rtc_output_dir"],
            config["dataset_name"],
            video_id.replace(config["video_suffix"], ".ivf"),
        )

        # Added exp name to separate different experiments
        detector_input_video = os.path.join(
            config["detector_input_dir"],
            config["experiment_id"],
            config["dataset_name"],
            video_id.replace(config["video_suffix"], ".mp4"),
        )

        # TODO
        if not os.path.exists(detector_input_video):
            with open(input_video_config_path, "r") as f:
                input_video_config = json.load(f)

                width = input_video_config["Width"]
                height = input_video_config["Height"]
                fps = input_video_config["Fps"]

                # Transcode
                encode_ret = encode_video(
                    rtc_output_video, detector_input_video, width, height, fps
                )
                if not encode_ret:
                    print(
                        f"Error encoding video {rtc_output_video} -> {detector_input_video}"
                    )
                return 1

        detector_input_videos.append(detector_input_video)

    # Done transcoding; generate detector input
    list_file_path = generate_detector_input(config)
    if not list_file_path:
        print("Error generating detector input list")
        return 1

    if config["symlink"] == True:
        create_deepfakebench_symlinks(config)

    # Done here unless segmented videos

    return 0


if __name__ == "__main__":
    exit(main())
