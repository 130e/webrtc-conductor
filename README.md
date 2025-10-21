# webrtc-experiment-conductor

```mermaid
graph LR
    Input_Video["`**Video**`"]

    Input_Video -.Transcode.-> Yuv["Raw Frames"]

    Yuv --> Orch("WebRTC Runner")
    Orch -.1_Frames.-> Local_Client("WebRTC Client A")
    
    Local_Client <-.2_Stream.-> Remote_Client
    Remote_Client -.3_Collect Result.-> Orch

    Orch --> ivf["Encoded Frames"]
    Orch --> log["RTC Packet Log"]
    ivf -.Transcode.-> Output_Video["`**Received Video**`"]
  
    ivf --> Aggr{Aggregate}
    log --> Aggr
    Aggr --> Frame_info["`**Frame Info**`"]
```

Pile of scripts to automate DF video generation, P2P video streaming experiment, trace collections, and post-processing.

- Orchestrate P2P WebRTC streaming experiment over two hosts
- Customized WebRTC native client
- Collect WebRTC packet logs and video dump
- Parse and format results for analysis

## Note

**Code hidden during submission**

## Instructions

The whole pipeline is controlled by a single yaml config file, for example: `config.yaml`
