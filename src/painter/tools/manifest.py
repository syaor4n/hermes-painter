"""Tool registries.

``TOOLS`` maps ``tool-name -> handler`` for the HTTP dispatcher in
``server.py``. ``MANIFEST`` is the GET /tool/manifest response shape —
ordered as-is, with each entry describing the handler's input/output so
callers (Claude Code / Hermes / MCP bridges) can wire it without pulling
the source.

The manifest order is load-bearing: consumers iterate it verbatim, and the
top entries (load_target / draw_strokes / score_plan) are the documented
"hello world" of the tool server. Reorder with care.
"""
from __future__ import annotations

from .analyze import (
    tool_analyze_target,
    tool_critique_canvas,
    tool_detect_faces,
    tool_direction_field_grid,
    tool_edge_map,
    tool_find_features,
    tool_gradient_field,
    tool_list_styles,
    tool_plan_style_schedule,
    tool_saliency_mask,
    tool_segment_regions,
)
from .canvas import (
    tool_clear,
    tool_draw_strokes,
    tool_dump_all,
    tool_dump_canvas,
    tool_dump_gaps,
    tool_dump_heatmap,
    tool_dump_target,
    tool_get_heatmap,
    tool_get_palette,
    tool_get_regions,
    tool_get_state,
    tool_load_target,
    tool_restore,
    tool_sample_grid,
    tool_sample_target,
    tool_score_plan,
    tool_snapshot,
)
from .memory import (
    tool_decay_skills,
    tool_list_journal,
    tool_list_skills,
    tool_load_painter_brief,
    tool_read_style,
    tool_record_reflection,
    tool_reflection_clusters,
    tool_save_journal_entry,
    tool_save_skill,
    tool_skill_effectiveness_report,
    tool_skill_promote,
    tool_update_style,
)
from .plans import (
    tool_accent_preserve_plan,
    tool_contour_stroke_plan,
    tool_detail_stroke_plan,
    tool_edge_stroke_plan,
    tool_face_detail_plan,
    tool_highlight_stroke_plan,
    tool_sculpt_correction_plan,
)
from . import duet_tool


TOOLS = {
    "load_target": tool_load_target,
    "draw_strokes": tool_draw_strokes,
    "score_plan": tool_score_plan,
    "get_heatmap": tool_get_heatmap,
    "get_regions": tool_get_regions,
    "get_state": tool_get_state,
    "dump_canvas": tool_dump_canvas,
    "dump_target": tool_dump_target,
    "dump_heatmap": tool_dump_heatmap,
    "dump_all": tool_dump_all,
    "sample_target": tool_sample_target,
    "find_features": tool_find_features,
    "get_palette": tool_get_palette,
    "dump_gaps": tool_dump_gaps,
    "edge_map": tool_edge_map,
    "gradient_field": tool_gradient_field,
    "analyze_target": tool_analyze_target,
    "plan_style_schedule": tool_plan_style_schedule,
    "edge_stroke_plan": tool_edge_stroke_plan,
    "detail_stroke_plan": tool_detail_stroke_plan,
    "contour_stroke_plan": tool_contour_stroke_plan,
    "saliency_mask": tool_saliency_mask,
    "direction_field_grid": tool_direction_field_grid,
    "highlight_stroke_plan": tool_highlight_stroke_plan,
    "sample_grid": tool_sample_grid,
    "segment_regions": tool_segment_regions,
    "decay_skills": tool_decay_skills,
    "skill_effectiveness_report": tool_skill_effectiveness_report,
    "reflection_clusters": tool_reflection_clusters,
    "sculpt_correction_plan": tool_sculpt_correction_plan,
    "detect_faces": tool_detect_faces,
    "face_detail_plan": tool_face_detail_plan,
    "accent_preserve_plan": tool_accent_preserve_plan,
    "critique_canvas": tool_critique_canvas,
    "record_reflection": tool_record_reflection,
    "load_painter_brief": tool_load_painter_brief,
    "clear": tool_clear,
    "snapshot": tool_snapshot,
    "restore": tool_restore,
    "list_skills": tool_list_skills,
    "save_skill": tool_save_skill,
    "list_journal": tool_list_journal,
    "save_journal_entry": tool_save_journal_entry,
    "read_style": tool_read_style,
    "update_style": tool_update_style,
    "skill_promote": tool_skill_promote,
    "list_styles": tool_list_styles,
    "paint_duet": duet_tool.tool_paint_duet,
    "list_personas": duet_tool.tool_list_personas,
}


MANIFEST = [
    {"name": "load_target", "input": {"path": "str"}, "output": {"classification": "dict"}},
    {"name": "draw_strokes", "input": {"strokes": "list[dict]", "reasoning": "str?"}, "output": {"score": "dict", "iteration": "int"}},
    {"name": "score_plan", "input": {"strokes": "list[dict]"}, "output": {"imagined": "dict (ssim, mse, delta_ssim)"}},
    {"name": "get_heatmap", "input": {}, "output": {"png_b64": "str"}},
    {"name": "get_regions", "input": {"top": "int?"}, "output": {"regions": "list"}},
    {"name": "get_state", "input": {}, "output": "full canvas+score+history"},
    {"name": "dump_canvas", "input": {}, "output": {"path": "str"}, "note": "writes /tmp/painter_canvas.png — Read it to see your work"},
    {"name": "dump_target", "input": {}, "output": {"path": "str"}},
    {"name": "dump_heatmap", "input": {}, "output": {"path": "str"}},
    {"name": "dump_all", "input": {}, "output": "canvas+target+heatmap paths"},
    {"name": "sample_target", "input": {"x":"int","y":"int","w":"int?","h":"int?"}, "output": {"rgb":"[r,g,b]","hex":"#rrggbb"}},
    {"name": "find_features", "input": {}, "output": {"sun":"{x,y,brightness,rgb}","horizon_y":"int","darkest_region":"{...}","warmth":"float","rule_of_thirds":"{...}"}},
    {"name": "get_palette", "input": {"n":"int?"}, "output": {"colors":"[{hex,rgb,weight}]"}},
    {"name": "dump_gaps", "input": {}, "output": {"path":"str","coverage":"0..1"}},
    {"name": "edge_map", "input": {"threshold":"float?"}, "output": {"path":"str","subject_region":"{x,y,w,h,edge_density}","edge_density":"float"}},
    {"name": "gradient_field", "input": {}, "output": {"quadrants":"{...}","suggested_direction":"'horizontal'|'vertical'|'random'"}},
    {"name": "analyze_target", "input": {}, "output": "full target strategy (classification+palette+features+edges+direction+grid suggestion)"},
    {
        "name": "plan_style_schedule",
        "input": {"target_analysis": "dict?"},
        "output": {"schedule": "{start, end, rationale}",
                   "candidates": "list[{start, end, score, reason}]"},
        "note": "Suggest a start→end style morph for the current target. "
                "Returns a primary schedule with a rationale, plus up to 3 "
                "ranked candidates (primary is always candidates[0]).",
    },
    {"name": "edge_stroke_plan", "input": {"max_strokes":"int|'auto'","percentile":"float?","width":"int?","alpha":"float?","min_length":"int?","sample_every":"int?","color_source":"'target'|'dark'","seed":"int?"}, "output": {"strokes":"list","n":"int","edge_pixel_count":"int","auto_budget":"int?"}},
    {"name": "detail_stroke_plan", "input": {"max_strokes":"int|'auto'","percentile":"float?","width":"int?","alpha":"float?","min_length":"int?","sample_every":"int?","color_source":"'target'|'dark'|'contrast'","seed":"int?"}, "output": {"strokes":"list","n":"int","edge_pixel_count":"int","auto_budget":"int?"}, "note": "thin-line finishing pass — run AFTER gap-fill"},
    {"name": "contour_stroke_plan", "input": {"sigma":"float?","min_length":"int?","max_strokes":"int|'auto'","width":"int?","alpha":"float?","color_source":"'target'|'dark'|'contrast'","stroke_type":"'bezier'|'polyline'","simplify_tolerance":"float?","focus_box":"[x,y,w,h]?","focus_boost":"float?","mask_path":"str?","mask_boost":"float?","seed":"int?"}, "output": {"strokes":"list","n":"int","n_components":"int","auto_budget":"int?","total_contour_pixels":"int"}, "note": "Canny+skeleton connected-component tracing. Default: painterly "
        "multi-stroke emission (3-8 overlapping bristle brush strokes per "
        "component with canvas-color sampling). Pass painterly=False to get "
        "the original uniform bezier/polyline per component."},
    {"name": "saliency_mask", "input": {"blur_sigma":"float?","center_bias":"float?","threshold":"float?"}, "output": {"path":"str","bbox":"[x,y,w,h]","fg_fraction":"float","separability":"float"}, "note": "Laplacian-variance foreground mask saved to /tmp/painter_saliency.png"},
    {"name": "direction_field_grid", "input": {"grid_size":"int?","coherence_floor":"float?"}, "output": {"grid":"list[list[{angle,coherence,mode}]]","grid_size":"int","cell_w":"int","cell_h":"int"}, "note": "Per-cell stroke direction via structure tensor"},
    {"name": "highlight_stroke_plan", "input": {"threshold":"int?","contrast_min":"int?","max_strokes":"int|'auto'","size_min":"int?","size_max":"int?","alpha":"float?","warm_tint":"float?","mask_path":"str?","seed":"int?"}, "output": {"strokes":"list","n":"int","candidates":"int","auto_budget":"int?"}, "note": "Catchlight dabs — run LAST, after contours"},
    {"name": "segment_regions", "input": {"n_segments":"int?","compactness":"float?","sigma":"float?"}, "output": {"path":"str","n_regions":"int","regions":"list[{id,centroid,bbox,pixel_count,mean_rgb,dominant_angle,coherence,palette}]"}, "note": "SLIC super-pixel segmentation with per-region palette + angle"},
    {"name": "sample_grid", "input": {"gx":"int?","gy":"int?"}, "output": {"grid":"list[list[hex]]","cell_w":"int","cell_h":"int"}, "note": "Batch cell-color sampling (replaces N² sample_target calls)"},
    {"name": "decay_skills", "input": {"days":"int?","dry_run":"bool?"}, "output": {"n_changed":"int","changes":"list","dry_run":"bool"}, "note": "#18: decrement confidence on skills untouched for N days"},
    {"name": "skill_effectiveness_report", "input": {"n":"int?"}, "output": {"recipes":"list","n_reflections":"int","failure_mode_total":"dict"}, "note": "v12.4: which recipes are used, how often, with what failures"},
    {"name": "reflection_clusters", "input": {"n":"int?"}, "output": {"clusters":"list[{mode,count,sample_runs,targets}]","clean_runs":"int","n_reflections":"int","summary":"str"}, "note": "v12.5: weekly review of recurring failure patterns"},
    {"name": "sculpt_correction_plan", "input": {"cell_size":"int?","error_threshold":"float?","mask_path":"str?","mask_threshold":"float?","max_strokes":"int|'auto'","stroke_width":"int?","alpha":"float?","seed":"int?"}, "output": {"strokes":"list","n":"int","high_error_cells":"int"}, "note": "v14: dense per-cell error correction — anatomy detail"},
    {"name": "detect_faces", "input": {"min_size":"int?","scale_factor":"float?","min_neighbors":"int?"}, "output": {"faces":"list[{x,y,w,h,source}]","n":"int"}, "note": "v15: opencv Haar frontal + profile face detection"},
    {"name": "face_detail_plan", "input": {"faces":"list","padding":"float?","cell_size":"int?","error_threshold":"float?","max_strokes_per_face":"int?","alpha":"float?","seed":"int?"}, "output": {"strokes":"list","n":"int","per_face":"list"}, "note": "v15: ultra-fine dab cluster inside face boxes for features"},
    {"name": "accent_preserve_plan", "input": {"chroma_threshold":"int?","min_region":"int?","max_regions":"int?","stroke_density":"int?","alpha":"float?","stroke_width":"int?","seed":"int?"}, "output": {"strokes":"list","n":"int","regions_found":"int"}, "note": "v17: preserve saturated accent regions (lips, eyeshadow, flags) that underpainting washes out"},
    {"name": "critique_canvas", "input": {"last_strokes":"list?"}, "output": {"findings":"list[{mode,severity,metric,fix}]","verdict":"'ok'|'minor'|'warn'|'fail'","suggested_fixes":"list[str]"}, "note": "Heuristic failure detectors — see painter-failure-modes skill"},
    {"name": "record_reflection", "input": {"run_id":"str?","target":"str","what_worked":"str","what_failed":"str","try_next_time":"str","confidence":"int 1-5","surprised_by":"str?","failure_modes":"list[str]?"}, "output": {"ok":"bool","path":"str"}, "note": "Structured post-run reflection — saved as markdown for session_search"},
    {"name": "load_painter_brief", "input": {}, "output": {"brief":"str (<2KB markdown)","size_bytes":"int"}, "note": "Compressed recap for session start — style + last runs + failure stats + top skills"},
    {"name": "clear", "input": {}, "output": {"ok": "bool"}},
    {"name": "snapshot", "input": {}, "output": {"id": "str"}},
    {"name": "restore", "input": {"id": "str"}, "output": {"ok": "bool"}},
    {"name": "list_skills", "input": {"image_type": "str?", "tags": "list[str]?"}, "output": {"skills": "list"}},
    {"name": "save_skill", "input": {"name": "str", "body": "str", "scope_types": "list[str]?", "tags": "list[str]?"}, "output": {"path": "str"}},
    {"name": "list_journal", "input": {"n": "int?"}, "output": {"entries": "list"}},
    {"name": "save_journal_entry", "input": {"run": "str?", "target": "str?", "image_type": "str?", "final_ssim": "float?", "note": "str?"}, "output": {"ok": "bool"}},
    {"name": "read_style", "input": {}, "output": {"body": "str"}},
    {"name": "update_style", "input": {"body": "str?", "evolution_note": "str?"}, "output": {"ok": "bool"}},
    {"name": "skill_promote",
     "input": {"n": "int?", "min_repeat": "int?", "max_promote": "int?", "dry_run": "bool?"},
     "output": {"promoted": "list", "bumped": "list", "scanned": "int"},
     "note": "Scan recent reflections (confidence ≥ 3); recurring 'what_worked' phrases become new skills (confidence=3) or bump existing."},
    {"name": "list_styles",
     "input": {},
     "output": {"styles": "list[{name,kind,extends?,parameters}]", "total": "int"},
     "note": "Built-in + community styles available for style_schedule / style_mode. "
             "kind is 'builtin' or 'community'; community entries include extends parent."},
    {
        "name": "paint_duet",
        "input": {
            "target": "str",
            "personas": "list[str|dict]?",
            "max_turns": "int?",
            "seed": "int?",
            "out_dir": "str?",
        },
        "output": {
            "canvas_path": "str", "journal_path": "str", "trace_path": "str",
            "turns": "list", "final_ssim": "float",
            "early_stopped": "bool", "reason": "str",
            "personas_used": "list[str]",
        },
        "note": "Run a two-persona critique-and-correct duet. Opening turn "
                "paints full canvas in persona[0]'s style; subsequent "
                "turns target worst cells filtered by each persona's "
                "taste. Rejects its own turn on SSIM regression.",
    },
    {
        "name": "list_personas",
        "input": {},
        "output": {"personas": "list[{name, style_mode, description, kind, source_path}]", "count": "int"},
        "note": "Enumerate registered personas (built-in + community via "
                "$PERSONAS_PATH). Mirror of list_styles for the persona "
                "registry.",
    },
]
