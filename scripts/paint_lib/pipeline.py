"""auto_paint — the multi-style target-driven pipeline (orchestrator).

Phase bodies have been extracted into scripts/paint_lib/phases_pkg/ as part
of CODE_REVIEW P2.11. This module now builds a PipelineContext, dispatches
on style_mode, and assembles the result dict.
"""
from __future__ import annotations

import datetime as _dt
import random as _random
import re as _re
import sys
from pathlib import Path

from .core import (
    post,
    track_phase,
    score_current_canvas,
    _regression_alert,
    _read_canvas_bytes,
)
from .phases_pkg._context import PipelineContext
from .phases_pkg._shared import _build_result_dict
from .phases_pkg import (
    analyze as _analyze,
    skill_feedback as _skill_feedback,
    underpaint as _underpaint,
    fog as _fog,
    edge as _edge,
    gap_fill as _gap_fill,
    detail as _detail,
    contour as _contour,
    highlight as _highlight,
    face_detail as _face_detail,
    sculpt as _sculpt,
    critique_correct as _critique_correct,
    score as _score_phase,
    reflect as _reflect,
)


# ---------------------------------------------------------------------------
# Sub-pipeline helpers
# ---------------------------------------------------------------------------

def _default_pipeline(ctx: PipelineContext) -> None:
    """Default layered pipeline: all phases in order."""
    _underpaint.run(ctx)
    _track_phase_score('underpainting', ctx)
    _edge.run(ctx)
    _gap_fill.run(ctx)
    _detail.run(ctx)
    _contour.run(ctx)
    _highlight.run(ctx)
    _face_detail.run(ctx)
    _sculpt.run(ctx)
    _critique_correct.run(ctx)

    _verbose_summary(ctx)


def _pointillism_pipeline(ctx: PipelineContext) -> None:
    """Pointillism short-circuit: dabs only, no finishing passes."""
    from .core import track_phase as _track_phase_core
    from .styles import pointillism_underpainting

    fine = post('sample_grid', {'gx': 64, 'gy': 64})
    fine_grid = fine['grid']
    strokes = pointillism_underpainting(
        ctx.grid, ctx.cell_w, ctx.cell_h, seed=ctx.seed,
        contrast_boost=ctx.contrast_boost,
        complementary_shadow=ctx.complementary_shadow,
        fine_grid=fine_grid,
    )
    post('draw_strokes', {'strokes': strokes, 'reasoning': 'Phase 1 · pointillism dabs'})
    ctx.underpaint_strokes = len(strokes)
    phase_deltas = {}
    ctx.current_score = _track_phase_core('pointillism', phase_deltas, ctx.target_path, None)
    ctx.phase_deltas = phase_deltas
    ctx.final_score = score_current_canvas(ctx.target_path)
    ctx.regression = _regression_alert(ctx.target_path, ctx.final_score, verbose=ctx.verbose) if ctx.final_score else None
    post('dump_canvas', {})
    if ctx.verbose:
        ssim_s = f"{ctx.final_score['ssim']:.3f}" if ctx.final_score else "?"
        print(f'  pointillism: {ctx.underpaint_strokes} dabs, ssim={ssim_s}')
    # coverage stays None for pointillism


def _tenebrism_pipeline(ctx: PipelineContext) -> None:
    """Tenebrism short-circuit: dark base + lit edges + fine detail + highlights + contours + sculpt."""
    from .core import track_phase as _track_phase_core
    from .styles import tenebrism_underpainting

    fine = post('sample_grid', {'gx': 64, 'gy': 64})
    fine_grid_cg = fine['grid']
    strokes = tenebrism_underpainting(
        ctx.grid, ctx.cell_w, ctx.cell_h, seed=ctx.seed,
        contrast_boost=ctx.contrast_boost,
        fine_grid=fine_grid_cg,
    )
    post('draw_strokes', {'strokes': strokes, 'reasoning': 'Phase 1 · tenebrism (dark base + light)'})
    ctx.underpaint_strokes = len(strokes)
    phase_deltas: dict = {}
    current_score = _track_phase_core('tenebrism', phase_deltas, ctx.target_path, None)

    edge_plan = post('edge_stroke_plan', {
        'max_strokes': 120, 'percentile': 88, 'width': 2, 'alpha': 0.75,
        'min_length': 8, 'color_source': 'target', 'seed': ctx.seed + 1,
    })
    if edge_plan.get('strokes'):
        post('draw_strokes', {'strokes': edge_plan['strokes'],
                               'reasoning': 'Phase 3 · tenebrism lit-edges'})
        ctx.edge_strokes = edge_plan['n']
        current_score = _track_phase_core('edges', phase_deltas, ctx.target_path, current_score)

    fine_plan = post('detail_stroke_plan', {
        'max_strokes': 'auto', 'percentile': 92, 'width': 1, 'alpha': 0.72,
        'min_length': 4, 'sample_every': 1, 'color_source': 'contrast',
        'mask_path': ctx.mask_path, 'mask_threshold': 0.15, 'seed': ctx.seed + 4,
    })
    if fine_plan.get('strokes'):
        post('draw_strokes', {'strokes': fine_plan['strokes'],
                               'reasoning': 'Phase 5b · tenebrism fine-detail'})
        ctx.fine_detail_strokes = fine_plan['n']
        current_score = _track_phase_core('fine_detail', phase_deltas, ctx.target_path, current_score)

    hl = post('highlight_stroke_plan', {
        'mask_path': ctx.mask_path, 'seed': ctx.seed + 6,
        'warm_tint': 0.35, 'threshold': 200,
    })
    if hl.get('strokes'):
        post('draw_strokes', {'strokes': hl['strokes'],
                               'reasoning': 'Phase 7 · tenebrism highlights'})
        ctx.highlight_strokes = hl['n']
        current_score = _track_phase_core('highlights', phase_deltas, ctx.target_path, current_score)

    contour_plan = post('contour_stroke_plan', {
        'sigma': 1.2, 'min_length': 8, 'max_strokes': 'auto',
        'width': 3, 'alpha': 0.78, 'color_source': 'contrast',
        'stroke_type': 'polyline', 'simplify_tolerance': 0.9,
        'mask_path': ctx.mask_path, 'mask_boost': 3.5,
        'skip_short_fraction': 0.10, 'seed': ctx.seed + 5,
        'painterly': True,
    })
    if contour_plan.get('strokes'):
        post('draw_strokes', {'strokes': contour_plan['strokes'],
                               'reasoning': 'Phase 6 · tenebrism contours'})
        ctx.contour_strokes = contour_plan['n']
        current_score = _track_phase_core('contours', phase_deltas, ctx.target_path, current_score)

    fine_contour_plan = post('contour_stroke_plan', {
        'sigma': 0.7, 'min_length': 5, 'max_strokes': 250,
        'width': 1, 'alpha': 0.65, 'color_source': 'contrast',
        'stroke_type': 'polyline', 'simplify_tolerance': 0.6,
        'mask_path': ctx.mask_path, 'mask_boost': 4.0,
        'skip_short_fraction': 0.0, 'seed': ctx.seed + 7,
        'painterly': False,
    })
    if fine_contour_plan.get('strokes'):
        post('draw_strokes', {'strokes': fine_contour_plan['strokes'],
                               'reasoning': 'Phase 6b · tenebrism fine-features'})
        ctx.contour_strokes += fine_contour_plan['n']
        current_score = _track_phase_core('fine_contours', phase_deltas, ctx.target_path, current_score)

    sp = post('sculpt_correction_plan', {
        'cell_size': 6, 'error_threshold': 28,
        'mask_path': ctx.mask_path, 'mask_threshold': 0.25,
        'max_strokes': 180, 'stroke_width': 5, 'alpha': 0.55,
        'seed': ctx.seed + 8,
    })
    if sp.get('strokes'):
        post('draw_strokes', {'strokes': sp['strokes'],
                               'reasoning': f'Phase 8 · sculpt (bristle, direction-aware, n={sp["n"]})'})
        ctx.sculpt_strokes = sp['n']
        current_score = _track_phase_core('sculpt', phase_deltas, ctx.target_path, current_score)

    ctx.phase_deltas = phase_deltas
    ctx.current_score = current_score
    ctx.final_score = score_current_canvas(ctx.target_path)
    ctx.regression = _regression_alert(ctx.target_path, ctx.final_score, verbose=ctx.verbose) if ctx.final_score else None
    post('dump_canvas', {})
    # coverage stays None for tenebrism


def _engraving_pipeline(ctx: PipelineContext) -> None:
    """Engraving short-circuit: hachures + contours only."""
    from .core import track_phase as _track_phase_core
    from .styles import engraving_underpainting

    strokes = engraving_underpainting(ctx.grid, ctx.cell_w, ctx.cell_h, seed=ctx.seed)
    post('draw_strokes', {'strokes': strokes, 'reasoning': 'Phase 1 · engraving hachures'})
    ctx.underpaint_strokes = len(strokes)
    phase_deltas: dict = {}
    current_score = _track_phase_core('engraving', phase_deltas, ctx.target_path, None)

    contour_plan = post('contour_stroke_plan', {
        'sigma': 1.6, 'min_length': 10, 'max_strokes': 'auto',
        'width': 1, 'alpha': 0.85, 'color_source': 'dark',
        'stroke_type': 'polyline', 'simplify_tolerance': 0.9,
        'skip_short_fraction': 0.20, 'mask_path': ctx.mask_path,
        'seed': ctx.seed + 5,
        'painterly': False,
    })
    if contour_plan['strokes']:
        post('draw_strokes', {'strokes': contour_plan['strokes'],
                               'reasoning': 'Phase 6 · engraving contours'})
        ctx.contour_strokes = contour_plan['n']
        current_score = _track_phase_core('contours', phase_deltas, ctx.target_path, current_score)

    ctx.phase_deltas = phase_deltas
    ctx.current_score = current_score
    ctx.final_score = score_current_canvas(ctx.target_path)
    ctx.regression = _regression_alert(ctx.target_path, ctx.final_score, verbose=ctx.verbose) if ctx.final_score else None
    post('dump_canvas', {})
    total = ctx.underpaint_strokes + ctx.contour_strokes
    if ctx.verbose:
        print(f'  engraving: {ctx.underpaint_strokes} hachures + {ctx.contour_strokes} contours = {total} strokes')
    # coverage stays None for engraving


# ---------------------------------------------------------------------------
# Helpers used by _default_pipeline
# ---------------------------------------------------------------------------

def _track_phase_score(name: str, ctx: PipelineContext) -> None:
    """Update ctx.current_score + ctx.phase_deltas after underpainting."""
    from .core import track_phase as _track_phase_core
    ctx.current_score = _track_phase_core(name, ctx.phase_deltas, ctx.target_path, None)


def _verbose_summary(ctx: PipelineContext) -> None:
    """Print the per-phase stroke summary when verbose=True."""
    if not ctx.verbose:
        return
    total = (ctx.underpaint_strokes + ctx.edge_strokes + ctx.fill_strokes
             + ctx.mid_detail_strokes + ctx.fine_detail_strokes
             + ctx.contour_strokes + ctx.highlight_strokes
             + ctx.impasto_strokes + ctx.face_detail_strokes
             + ctx.sculpt_strokes + ctx.dense_sculpt_strokes
             + ctx.critique_strokes)
    print(
        f'  {ctx.underpaint_strokes} under + {ctx.edge_strokes} edges + {ctx.fill_strokes} fills '
        f'+ {ctx.mid_detail_strokes} mid + {ctx.fine_detail_strokes} fine '
        f'+ {ctx.contour_strokes} contours + {ctx.highlight_strokes} highlights '
        f'+ {ctx.critique_strokes} critique = '
        f'{total} strokes, coverage {ctx.gaps_coverage:.1%}'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def auto_paint(target_path, seed=0, verbose=True, contrast_boost=0.25,
               use_saliency=True, use_local_direction=True, use_highlights=True,
               use_segmentation=False, n_segments=8,
               critique_rounds=0, grayscale=None,
               complementary_shadow=0.12, style_mode=None,
               painterly_details=False, use_face_detail=True,
               auto_reflect=False, apply_feedback=True,
               style_schedule=None):
    """Generic auto-painter. Analyzes target, picks parameters, paints in phases:
      0. Saliency mask
      1. Underpainting (bristle / engraving / pointillism / tenebrism / van_gogh)
      2. Optional fog
      3. Edges
      4. Gap-fill if coverage < 95%
      5a/5b. Mid + fine detail (mask-aware)
      6. Contours (Canny skeletons → bezier)
      7. Highlights

    apply_feedback: when True (default), read skills applicable to the target's
      image_type and bias parameters via dimensional_effects. Disable if you
      want a clean baseline paint for benchmarking.
    auto_reflect: when True, write a reflection + journal entry at the end.
      Default False (batch scripts enable it explicitly).

    Returns a dict with phase counts + final coverage.
    """
    from . import morph as _morph

    # --- Morph schedule handling ---
    if style_schedule is not None:
        _morph.validate_schedule(style_schedule)
        style_mode = style_schedule["start"]
    _phase_blends = None
    if style_schedule is not None:
        _phase_blends = list(_morph.PHASE_T.values())

    post('clear', {})

    ctx = PipelineContext(
        target_path=target_path,
        seed=seed,
        verbose=verbose,
        contrast_boost=contrast_boost,
        use_saliency=use_saliency,
        use_local_direction=use_local_direction,
        use_highlights=use_highlights,
        use_segmentation=use_segmentation,
        n_segments=n_segments,
        critique_rounds=critique_rounds,
        grayscale=grayscale,
        complementary_shadow=complementary_shadow,
        style_mode=style_mode,
        painterly_details=painterly_details,
        use_face_detail=use_face_detail,
        auto_reflect=auto_reflect,
        apply_feedback=apply_feedback,
        style_schedule=style_schedule,
        phase_blends=_phase_blends,
    )

    # Phase 0a: classify target, fetch strategy, saliency mask
    _analyze.run_pre(ctx)

    # Phase 0b: apply skill feedback (may update style_mode, contrast_boost, etc.)
    _skill_feedback.run(ctx)

    # Phase 0c: grayscale detection + grid sampling + direction field
    # (must follow skill_feedback: style_mode and contrast_boost are now final)
    _analyze.run_post(ctx)

    # Dispatch to style-specific sub-pipeline
    if ctx.style_mode == 'pointillism':
        _pointillism_pipeline(ctx)
        result = _build_result_dict(ctx)
        if ctx.auto_reflect:
            _reflect.run(ctx)
            result['reflection_path'] = ctx.reflection_path
            result['journal_path'] = ctx.journal_path
        return result

    if ctx.style_mode == 'tenebrism':
        _tenebrism_pipeline(ctx)
        result = _build_result_dict(ctx)
        if ctx.auto_reflect:
            _reflect.run(ctx)
            result['reflection_path'] = ctx.reflection_path
            result['journal_path'] = ctx.journal_path
        return result

    if ctx.style_mode == 'engraving':
        _engraving_pipeline(ctx)
        result = _build_result_dict(ctx)
        if ctx.auto_reflect:
            _reflect.run(ctx)
            result['reflection_path'] = ctx.reflection_path
            result['journal_path'] = ctx.journal_path
        return result

    # Default layered pipeline
    _default_pipeline(ctx)

    # Score + coverage
    _score_phase.run(ctx)
    _reflect.run(ctx)

    return _build_result_dict(ctx)


# ---------------------------------------------------------------------------
# Auto-reflection helper (kept for backward compat; logic moved to reflect.py)
# ---------------------------------------------------------------------------

def _slug(text: str, maxlen: int = 40) -> str:
    s = _re.sub(r'[^a-z0-9]+', '_', Path(text).stem.lower()).strip('_')
    return s[:maxlen] or 'untitled'


def _record_target_run(target_path: str, image_type: str, style_mode: str | None,
                        seed: int, result: dict) -> tuple[str | None, str | None]:
    """Write reflections/<run_id>.md + append to journal.jsonl for a target run.
    Kept for backward compatibility. New code should use phases_pkg.reflect.run().
    """
    try:
        run_id = f'target_{_dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")}_{_slug(target_path)}'
        score = result.get('final_score') or {}
        ssim = score.get('ssim')
        bits = []
        if style_mode:
            bits.append(f'style_mode={style_mode}')
        bits.append(f'image_type={image_type}')
        if ssim is not None and ssim >= 0.40:
            bits.append(f'ssim_ok={ssim:.2f}')
        if result.get('mask_used'):
            bits.append('saliency_mask')
        what_worked = '; '.join(bits) or 'defaults'
        fails = []
        if ssim is not None and ssim < 0.30:
            fails.append('low_ssim')
        cov = result.get('coverage')
        if cov is not None and cov < 0.95:
            fails.append(f'coverage_low={cov:.2f}')
        if (result.get('regression') or {}).get('delta', 0) < -0.02:
            fails.append('regression_vs_prev')
        what_failed = '; '.join(fails) or 'none detected'
        _SSIM_OK = {
            'dark': (0.15, 0.25), 'muted': (0.20, 0.30), 'bright': (0.30, 0.42),
            'high_contrast': (0.25, 0.34), 'balanced': (0.20, 0.28),
        }
        fail_thr, ok_thr = _SSIM_OK.get(image_type, (0.30, 0.40))
        confidence = 3
        if ssim is None or ssim < fail_thr:
            confidence = 1
        elif ssim < ok_thr:
            confidence = 2
        try:
            post('record_reflection', {
                'run_id': run_id, 'target': target_path,
                'what_worked': what_worked, 'what_failed': what_failed,
                'try_next_time': '', 'confidence': confidence, 'failure_modes': [],
            })
            reflection_path = f'reflections/{run_id}.md'
        except Exception:
            reflection_path = None
        try:
            entry = {
                'run': run_id, 'target': target_path, 'image_type': image_type,
                'style_mode': style_mode, 'seed': seed,
                'final_ssim': ssim,
                'n_strokes_under': result.get('underpaint_strokes', 0),
                'n_strokes_detail': (result.get('mid_detail_strokes', 0)
                                      + result.get('fine_detail_strokes', 0)),
                'n_strokes_contour': result.get('contour_strokes', 0),
                'coverage': cov, 'note': what_worked,
            }
            post('save_journal_entry', entry)
            journal_path = 'journal.jsonl'
        except Exception:
            journal_path = None
        return reflection_path, journal_path
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# auto_paint_best_of — unchanged
# ---------------------------------------------------------------------------

def auto_paint_best_of(target_path, n_seeds=3, base_seed=0, verbose=True,
                        critique_rounds=0, **kwargs):
    """Run auto_paint n_seeds times with different seeds, keep the best (lowest composite).
    Re-runs the winning seed on the live canvas at the end.
    """
    _here = Path(__file__).resolve().parent.parent
    _src = _here.parent / 'src'
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    target_bytes = Path(target_path).read_bytes()

    best = None
    all_runs = []
    for i in range(n_seeds):
        seed = base_seed + i * 17
        if verbose:
            print(f'\n— seed {seed} ({i+1}/{n_seeds}) —')
        result = auto_paint(target_path, seed=seed, verbose=verbose,
                            critique_rounds=critique_rounds, **kwargs)
        post('dump_canvas', {})
        canvas_bytes = _read_canvas_bytes()
        if canvas_bytes is None:
            continue
        from painter.critic import score as score_fn
        sc = score_fn(target_bytes, canvas_bytes)
        result['score'] = sc
        result['seed'] = seed
        result['canvas_png'] = canvas_bytes
        all_runs.append(result)
        if verbose:
            print(f'  ↳ ssim={sc["ssim"]:.4f} mse={sc["mse"]:.5f} composite={sc["composite"]:.4f}')
        if best is None or sc['composite'] < best['score']['composite']:
            best = result

    if best and best['seed'] != all_runs[-1]['seed']:
        if verbose:
            print(f'\nBest = seed {best["seed"]} (composite={best["score"]["composite"]:.4f}); restoring')
        post('clear', {})
        post('load_target', {'path': target_path})
        result = auto_paint(target_path, seed=best['seed'], verbose=False,
                            critique_rounds=critique_rounds, **kwargs)
        result['score'] = best['score']
        result['seed'] = best['seed']
        best = result

    summary = [{'seed': r['seed'], 'score': r['score'],
                'coverage': r.get('coverage')} for r in all_runs]
    if best is not None:
        best['all_runs'] = summary
    return best
