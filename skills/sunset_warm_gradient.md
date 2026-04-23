---
scope:
  image_types: ['balanced']
  exclude: []
provenance:
  created: 2026-04-20
  run: live_cli_demo
  delta_ssim: 0.6859
confidence: 1
tags: ['sunset', 'warm', 'gradient']
---
For balanced/warm sunset targets, the big SSIM win comes from two coarse fill_rect: warm top band (~55-60% of height, orange-red) + dark band below (purple-blue). Any attempt at detailed gradients via multiple thin bands or bezier curves REGRESSES SSIM — the metric penalizes structured edges that don't exist in smooth target gradients. Once at ~0.68 SSIM, further improvements come from MSE (local patches) not SSIM (global structure). Stop early or accept the trade-off.
