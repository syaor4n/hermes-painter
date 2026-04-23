## Batch Patching — Key Discovery

### The insight
Fixing patches ONE BY ONE across iterations causes neighboring patches to shift,
creating new errors. Fixing MANY patches at ONCE in a single iteration avoids this.

### The numbers
- Incremental (10 patches per iteration): +0.001 SSIM per iteration
- Batch (200 patches per iteration): +0.007 to +0.009 SSIM per iteration
- Batch is 7-9x more effective per iteration

### Workflow
1. Compute error map (|target - current| per pixel)
2. For each 8x8 or 16x16 block, compute mean error
3. For blocks above threshold, use target's average color as fix
4. Apply ALL fixes in one batch (200-300 strokes per batch)

### Threshold schedule
- First pass: error > 120 (fix gross errors)
- Second pass: error > 80 (medium errors)
- Third pass: error > 40 (fine errors)
- Fourth pass: error > 30 (polish)

### When discovered
Session 1, during the landscape photo painting.
Switching from manual 10-patch fixes to 200-patch batches was the single
biggest efficiency improvement in the entire project.
