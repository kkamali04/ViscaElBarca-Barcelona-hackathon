# Primary-source research — November 16, 2026

Tools: Exa semantic search/fetch and Firecrawl developer search/live scrape.
Public organizer docs were read locally; no restricted assets were sent to tools.

| Source | What it establishes | Decision for this task |
| --- | --- | --- |
| [Organizer CHALLENGE](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/CHALLENGE.md) | Phase1 predicts team possession; tracking is already supplied. Replacement vision is allowed, not required. | Repair coordinate replay without introducing a vision dependency. |
| [Organizer DATA](https://github.com/metrica-sports/more-than-a-hack-2027/blob/main/DATA.md) | ATD includes player/ball coordinates with fragmented anonymous slots and missing observations. Tactical frame0 corresponds to ATD record1. | Preserve exact alignment and missingness; never claim stable player/jersey identities. |
| [NVIDIA Gst-nvtracker](https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_plugin_gst-nvtracker.html) | DeepStream associates detected objects across frames; NvSORT uses boxes/Kalman filtering, NvDeepSORT adds ReID, NvDCF uses visual correlation, MaskTracker adds SAM2 segmentation. | A legitimate future video pipeline, but it does not fix a static SVG or infer possession by itself. |
| [Meta SAM3 repository](https://github.com/facebookresearch/sam3) | Promptable image/video segmentation, detection and tracking; repo announces SAM3.1 multiplexing. Installation requires a CUDA GPU/PyTorch, and checkpoint access is requested separately. | Adds a substantial new vision stack and access prerequisites; no installation for an existing-coordinate viewer. |
| [Meta CoTracker](https://github.com/facebookresearch/co-tracker) | Tracks points in video; online chunks can reduce memory relative to loading an entire video. CUDA recommended; CPU possible for small tasks. | A point tracker is distinct from a complete football player/ball detector and possession model. |

The live NVIDIA page and search snapshots expose different SDK versions; do not
derive a release pin or local performance promise from those snapshots. No
third-party FPS number is a measurement on this user's match/hardware.

The current UI problem is independently reproducible from public source: fixed
SVG circles, sine-wave ball movement and lost time from clamping each callback's
elapsed time. Replaying existing observations is the smallest useful change.
This conclusion is an engineering judgment from source inspection, not a claim
that alternative vision models cannot improve the noisy input in a future study.

Implementation reuse: frozen strict metadata/channel validation in
possession_model/features.py can be called without FeatureAccumulator. The old
feature output contains aggregate player geometry and ball positions, not full
player trajectories. Therefore build a separate bounded disk replay index; do
not pretend a possession CSV can reconstruct object motion.

Research limits: bounded official-source review, no exhaustive tracker benchmark,
no actual video-model trial, no local GPU/VRAM claim and no new detection accuracy
claim. Preserve the model/submission before the deadline.
