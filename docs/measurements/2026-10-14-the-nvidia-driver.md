# The NVIDIA driver and KVMem's crashes

**When:** 2026-10-13 and 10-14, in Clank's development sessions on the owner's machine; written down on 2026-10-20.

**Question:** KVMem began to crash with CUDA errors on 2026-10-13, the day the NVIDIA app installed a new driver. Was
the driver the cause?

**The machine:** an RTX 5080 under Windows 11, KVMem v0.16.0-rc1 (built with CUDA 13.2) in WSL 2's Ubuntu 22.04. One
machine only: this says nothing of the drivers on other cards.

## On driver 617.42

The NVIDIA app installed driver 617.42 on 2026-10-13, in place of 610.88, which had run without trouble.

- **KVMem crashed on clearing its cache.** KVMem keeps one conversation, and clears its cache when a request belongs to
  another (design 0012 §3). On 617.42, 2 of 9 such clears crashed it with a CUDA error at `cudaStreamSynchronize`, in
  `ggml_backend_cuda_buffer_clear`. The 36 clears before the update had crashed none.
- **Windows logged the driver's trouble.** The display driver's event 153 (`nvlddmkm`) came ten times that night,
  against once in the 40 days before.

## On driver 591.74

The owner installed driver 591.74 on 2026-10-14, and the same work was run again, and more: 66 cache clears in 81
turns. Of the clears, 62 came from a scripted conversation with tools that alternated with a title request, and the
rest from three OpenCode sessions run without their interface. There was no CUDA error, and one engine process ran
throughout. On 2026-10-20 `clank doctor` still reports 591.74.

## What it shows

On this machine, driver 617.42 crashed KVMem's cache clears, and 591.74 and 610.88 did not. So:

- **Stay on 591.74** (or 610.88).
- **Keep the NVIDIA app from updating the driver by itself.**
- **If KVMem starts crashing with CUDA errors after a driver change, roll the driver back first**, before looking
  anywhere else. `clank doctor` shows the driver's version.
