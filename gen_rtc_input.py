#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
from typing import List
from pathlib import Path


def find_files(dir: str, suffix: str) -> List[str]:
    results: List[str] = []
    for root, _, files in os.walk(dir):
        for filename in files:
            if filename.lower().endswith(suffix):
                file_path = os.path.join(root, filename)
                results.append(file_path)
    return results


def process_video(video_path: str, output_path: str, overwrite: bool = False):
    # Convert video
    if not overwrite and os.path.exists(output_path):
        # print(f"Skipping {output_path} because it already exists")
        pass
    else:
        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-pix_fmt",
            "yuv420p",
            "-y",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.returncode != 0:
            print(f"Error processing {video_path}: {result.stderr}")
            return ""

    # Generate config
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Find 1st video stream
    video_stream = None
    for stream in data["streams"]:
        if stream["codec_type"] == "video":
            video_stream = stream
            break

    if not video_stream:
        print(f"No video stream found for {video_path}")
        return ""

    # Extract duration from format
    duration = float(data["format"]["duration"])
    duration_ms = int(duration * 1000)

    # Generate config
    config = {
        "Width": video_stream["width"],
        "Height": video_stream["height"],
        "Fps": int(eval(video_stream["r_frame_rate"])),
        "OriginalDurationMS": duration_ms,
        "VideoPath": output_path,
        "DurationMS": duration_ms + 60000,
    }

    config_path = output_path.replace(".yuv", ".json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    return config_path


def main():
    parser = argparse.ArgumentParser(description="Generate RTC input")
    parser.add_argument("--input", "-i", type=str, required=True)
    parser.add_argument("--dataset", "-d", type=str, required=True)
    parser.add_argument("--suffix", type=str, default=".mp4")
    args = parser.parse_args()

    output_base_dir = "./data/rtc_input"

    # Process all files in the input directory
    video_files = find_files(args.input, args.suffix)
    print(f"Found {len(video_files)} files")

    config_files = []

    for video in video_files:
        # prepare path
        rel_path = os.path.relpath(video, start=args.input)
        output_video = os.path.join(output_base_dir, args.dataset, rel_path)
        output_video = output_video.replace(args.suffix, ".yuv")
        os.makedirs(os.path.dirname(output_video), exist_ok=True)
        config_file = process_video(video, output_video)
        if not config_file:
            print(f"Error processing {video}")
            break
        config_files.append(config_file)
        # print(f"Processed {video} -> {config_file}")

    with open(f"config_summary_{args.dataset}.log", "w") as f:
        for config_file in config_files:
            f.write(config_file + "\n")

    print(f"Processed {len(config_files)} files")


if __name__ == "__main__":
    exit(main())
