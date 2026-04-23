"""Shared mutable state for a single auto_paint run.

Every phase reads and writes fields on this dataclass. Flow is
sequential — phases run in order and the next phase sees the previous
phase's mutations.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PipelineContext:
    # --- inputs (never mutated) ---
    target_path: str
    seed: int = 0
    verbose: bool = True
    style_mode: str | None = None
    style_schedule: dict | None = None

    # --- target analysis (populated in analyze phase) ---
    image_type: str = "balanced"
    grid_size: int = 16
    direction: str = "horizontal"
    fog_hint: bool = False
    edge_density: float = 0.0
    saliency_info: dict | None = None
    mask_path: str | None = None
    grid: list[list[str]] | None = None
    cell_w: int = 0
    cell_h: int = 0
    direction_grid: list[list[dict]] | None = None
    strategy: dict = field(default_factory=dict)
    segmentation_info: dict | None = None

    # --- parameters (bias-adjusted via skill_feedback phase) ---
    contrast_boost: float = 0.25
    complementary_shadow: float = 0.12
    critique_rounds: int = 0
    painterly_details: bool = False
    grayscale: bool | None = None
    use_saliency: bool = True
    use_local_direction: bool = True
    use_highlights: bool = True
    use_segmentation: bool = False
    n_segments: int = 8
    use_face_detail: bool = True
    apply_feedback: bool = True
    auto_reflect: bool = False

    # --- running state (mutated across phases) ---
    current_score: dict | None = None
    phase_deltas: dict = field(default_factory=dict)
    applied_skills: list = field(default_factory=list)
    effective_params: dict | None = None
    phase_blends: list[float] | None = None

    # --- stroke counters (written by each phase, read into result) ---
    underpaint_strokes: int = 0
    fog_strokes: int = 0
    edge_strokes: int = 0
    fill_strokes: int = 0
    mid_detail_strokes: int = 0
    fine_detail_strokes: int = 0
    contour_strokes: int = 0
    highlight_strokes: int = 0
    face_detail_strokes: int = 0
    sculpt_strokes: int = 0
    dense_sculpt_strokes: int = 0
    critique_strokes: int = 0
    impasto_strokes: int = 0  # kept at 0 for result-dict shape stability

    # --- extra per-phase metadata (written by individual phases) ---
    edge_budget: int | None = None
    contour_components: int = 0
    highlight_candidates: int = 0
    gaps_coverage: float = 0.0  # last measured gap coverage

    # --- finishing shared (reused across detail / contour / highlight) ---
    finishing_shared: dict = field(default_factory=dict)

    # --- final artifacts (written by score + reflect phases) ---
    final_score: dict | None = None
    regression: dict | None = None
    coverage: float | None = None
    reflection_path: str | None = None
    journal_path: str | None = None
