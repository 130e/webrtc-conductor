# webrtc-conductor

Pile of scripts to automate DF video generation, P2P video streaming experiment, trace collections, and post-processing.

- Orchestrate P2P WebRTC streaming test over two hosts using native clients
- Collect WebRTC packet logs and video dump
- Parse and format results for analysis

## Instructions

The whole pipeline is controlled by a single yaml config file, for examples: `Celeb-DF-v1-config.yaml`.

**NOTE**: Blind, hidden...

### DF Generation

Generate a set of videos for streaming.

### Real-time Streaming Experiment

Batch run WebRTC video streaming experiment between two hosts using native webrtc clients

### Detector

At this point, you have detector results for each video and frames, as well as overall acc, auc, etc.
