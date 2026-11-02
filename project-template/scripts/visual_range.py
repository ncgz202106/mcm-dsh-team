"""Guard plotted points and intervals against silent axis clipping.

Call after the final axis limits are set. This inspects supplied numerical
coordinates, not text layout, scientific validity, or a screenshot's beauty.
No values are clipped, imputed, resampled or altered by this helper.
"""
import math


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean values are not plot measurements')
    try:
        value=float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError('Expected a one-dimensional numerical series') from exc
    if math.isinf(value):
        raise ValueError('Infinite plot coordinates are not supported')
    return None if math.isnan(value) else value


def require_visible_data(values, limits, *, lower=None, upper=None,
                         allow_undefined=False, tolerance=1e-12, context='series'):
    """Raise when any supplied defined point or interval is outside the axis.

    ``limits`` should come from the FINAL ``ax.get_xlim()``/``get_ylim()``.
    Lower and upper must both be supplied, or both omitted. Undefined points
    require an explicit policy and undefined interval ends; they are counted,
    never converted to zero. Inverted axes are supported. This is deliberately
    not a substitute for checking source IDs, definitions and actual rendering.
    """
    bounds=list(limits)
    if len(bounds)!=2:
        raise ValueError('Provide exactly two axis limits')
    bounds=[_number(x) for x in bounds]
    if None in bounds or bounds[0]==bounds[1]:
        raise ValueError('Axis limits must be finite and distinct')
    lo,hi=sorted(bounds)
    if isinstance(tolerance,bool) or not math.isfinite(tolerance) or tolerance<0:
        raise ValueError('Tolerance must be finite and nonnegative')
    vals=[_number(x) for x in values]
    if not vals:
        raise ValueError('An empty series cannot establish data visibility')
    if (lower is None)!=(upper is None):
        raise ValueError('Both interval ends are required')
    has_intervals=lower is not None
    lows=[_number(x) for x in lower] if has_intervals else list(vals)
    highs=[_number(x) for x in upper] if has_intervals else list(vals)
    if len(vals)!=len(lows) or len(vals)!=len(highs):
        raise ValueError('Point and interval lengths differ')
    defined=[];undefined=0
    for i,(point,left,right) in enumerate(zip(vals,lows,highs)):
        if point is None:
            if not allow_undefined or left is not None or right is not None:
                raise ValueError(f'{context}[{i}]: undefined point needs an explicit consistent policy')
            undefined+=1
            continue
        if left is None or right is None or left>right:
            raise ValueError(f'{context}[{i}]: missing or reversed interval')
        if min(point,left)<lo-tolerance or max(point,right)>hi+tolerance:
            raise ValueError(f'{context}[{i}]: point/interval outside final axis limits [{lo}, {hi}]')
        defined.extend((point,left,right))
    if not defined:
        raise ValueError('No defined point: use an explicitly labelled missing-state panel')
    return {'points':len(vals),'defined_points':len(vals)-undefined,
        'undefined_points':undefined,'intervals_checked':has_intervals,
        'axis_limits':[lo,hi],'data_extent':[min(defined),max(defined)],
        'passed':True,'visual_review':'still_required'}
