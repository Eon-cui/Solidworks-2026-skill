"""COM API signatures — single source of truth for verified SW2026 FeatureManager parameters.
Each signature is a factory function that returns the correct parameter tuple.
Adding a new SW version? Add a version param, keep backward compat.

Three-site audit (2026-06-29):
  FeatureCut3: sw_session.SW.cut / sw_part.extrude_cut / mcp server sw_feature_extrude_cut
    — 26 params identical EXCEPT mcp server exposes draft angle at Dang1 (pos 12, 0.0 in the other two).
  FeatureExtrusion3: sw_session.SW.extrude / sw_part.extrude_boss / sw_part.extrude_midplane
    — 23 params identical EXCEPT sw_part exposes `merge` at pos 19 (True in sw_session),
      and extrude_midplane uses end_condition=6 (midplane) at pos 4.

The canonical signatures below correspond to sw_session.py (the most battle-tested, 35+ part builds).
Callers with divergent needs (draft, midplane) should use the factory params, not copy tuples.
"""


def feature_cut3_params(through_all=False, depth_m=0.0, flip=False, normal_cut=False, dir_flag=False):
    """FeatureCut3 26-parameter verified signature (makepy 实测).

    Iron law: flip=False, normal_cut=False, dir=auto-retry (caller handles).
    Returns: tuple of 26 args ready for fm.FeatureCut3(*args)

    Parameters:
      through_all: True → end condition = ThroughAll (ignores depth_m)
      depth_m:     blind depth in meters (SW API unit)
      flip:        True → cut direction reversed (WARNING: may cut opposite body!)
      normal_cut:  True → NORMAL-CUT (WARNING: True = 静默失败, always use False!)
      dir_flag:    True → flip cut direction in 2D sketch plane
    """
    t1 = 1 if through_all else 0
    d1 = 0.001 if through_all else depth_m
    return (
        True, flip, dir_flag, t1, 0, d1, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        normal_cut,
        True, True, True, True, False,
        0, 0.0, False,
    )


def feature_extrusion3_params(depth_m=0.0, reverse=False, merge=True, end_condition=0):
    """FeatureExtrusion3 23-parameter verified signature.

    Returns: tuple of 23 args ready for fm.FeatureExtrusion3(*args)

    Parameters:
      depth_m:       blind depth in meters (SW API unit)
      reverse:       True → flip extrusion direction
      merge:         True → merge result with existing bodies
      end_condition: 0=Blind, 1=ThroughAll, 6=Midplane (swPartEndCond_e)
    """
    return (
        True, reverse, False, end_condition, 0, depth_m, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False,
        merge, False, True, 0, 0.0, False,
    )
