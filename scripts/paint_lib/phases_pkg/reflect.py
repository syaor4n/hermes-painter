"""Phase 14: Auto-reflect persistence (save_journal_entry + record_reflection). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

import datetime as _dt
import re as _re
from pathlib import Path

from ._context import PipelineContext
from ._shared import _warn


NAME = "reflect"


def _slug(text: str, maxlen: int = 40) -> str:
    s = _re.sub(r'[^a-z0-9]+', '_', Path(text).stem.lower()).strip('_')
    return s[:maxlen] or 'untitled'


def run(ctx: PipelineContext) -> None:
    """Write reflections/<run_id>.md + append to journal.jsonl.

    Gate: ctx.auto_reflect must be True.
    """
    from ..core import post

    if not ctx.auto_reflect:
        return

    try:
        run_id = (
            f'target_{_dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")}'
            f'_{_slug(ctx.target_path)}'
        )
        score = ctx.final_score or {}
        ssim = score.get('ssim')

        bits = []
        if ctx.style_mode:
            bits.append(f'style_mode={ctx.style_mode}')
        bits.append(f'image_type={ctx.image_type}')
        if ssim is not None and ssim >= 0.40:
            bits.append(f'ssim_ok={ssim:.2f}')
        if ctx.mask_path:
            bits.append('saliency_mask')
        if ctx.painterly_details or (ctx.effective_params or {}).get('painterly_details'):
            bits.append('painterly')
        if (ctx.effective_params or {}).get('critique_rounds', 0) > 0:
            bits.append('critique_correction')
        what_worked = '; '.join(bits) or 'defaults'

        fails = []
        if ssim is not None and ssim < 0.30:
            fails.append('low_ssim')
        cov = ctx.coverage
        if cov is not None and cov < 0.95:
            fails.append(f'coverage_low={cov:.2f}')
        if (ctx.regression or {}).get('delta', 0) < -0.02:
            fails.append('regression_vs_prev')
        what_failed = '; '.join(fails) or 'none detected'

        _SSIM_OK = {
            'dark':          (0.15, 0.25),
            'muted':         (0.20, 0.30),
            'bright':        (0.30, 0.42),
            'high_contrast': (0.25, 0.34),
            'balanced':      (0.20, 0.28),
        }
        fail_thr, ok_thr = _SSIM_OK.get(ctx.image_type, (0.30, 0.40))
        confidence = 3
        if ssim is None or ssim < fail_thr:
            confidence = 1
        elif ssim < ok_thr:
            confidence = 2

        try:
            post('record_reflection', {
                'run_id': run_id,
                'target': ctx.target_path,
                'what_worked': what_worked,
                'what_failed': what_failed,
                'try_next_time': '',
                'confidence': confidence,
                'failure_modes': [],
            })
            ctx.reflection_path = f'reflections/{run_id}.md'
        except Exception as exc:
            _warn("record_reflection", exc)
            ctx.reflection_path = None

        try:
            entry = {
                'run': run_id,
                'target': ctx.target_path,
                'image_type': ctx.image_type,
                'style_mode': ctx.style_mode,
                'seed': ctx.seed,
                'final_ssim': ssim,
                'n_strokes_under': ctx.underpaint_strokes,
                'n_strokes_detail': ctx.mid_detail_strokes + ctx.fine_detail_strokes,
                'n_strokes_contour': ctx.contour_strokes,
                'coverage': cov,
                'note': what_worked,
            }
            post('save_journal_entry', entry)
            ctx.journal_path = 'journal.jsonl'
        except Exception as exc:
            _warn("save_journal_entry", exc)
            ctx.journal_path = None

    except Exception as exc:
        _warn("persist_reflection", exc)
        ctx.reflection_path = None
        ctx.journal_path = None
