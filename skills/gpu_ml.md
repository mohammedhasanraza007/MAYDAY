---
triggers: [gpu, nvidia, cuda, ml, machine learning, model, inference, pytorch, tensorflow, embedding, acceleration]
---
GPU AND ML RULES:
- Always check gpu_detector.get_info() before recommending GPU-specific configurations.
- For NVIDIA hardware: CUDA is preferred; n_gpu_layers should be set based on VRAM.
- For AMD hardware: DirectML or Vulkan; do not recommend CUDA.
- For CPU-only: use llama-cpp-python with AVX2; never recommend GPU-only libraries.
- Local GGUF inference always takes priority over cloud API for privacy-sensitive tasks.
- Optional ML dependencies (torch, sentence-transformers) must never be hard-required.
