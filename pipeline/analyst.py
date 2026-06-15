"""
Content classification and metrics.
Hook type classification, format detection, engagement calculations.
"""


def classify_hooks(captions):
    """Classify caption hooks into types based on first line patterns."""
    types = {
        'question': 0, 'curiosity': 0, 'philosophy': 0, 'story': 0,
        'negative': 0, 'achievement': 0, 'contrarian': 0, 'direct_cta': 0,
        'empathy': 0, 'authority': 0, 'other': 0
    }
    for cap in captions:
        if not cap:
            continue
        first_line = cap.split('\n')[0].lower().strip()
        if '?' in first_line:
            types['question'] += 1
        elif any(w in first_line for w in ['secret', 'hidden', 'nobody', 'most people', 'what if']):
            types['curiosity'] += 1
        elif any(w in first_line for w in ['stop', "don't", 'never', 'warning', 'mistake']):
            types['negative'] += 1
        elif any(w in first_line for w in ['i was', 'my story', 'when i', 'years ago']):
            types['story'] += 1
        elif any(w in first_line for w in ['dm', 'book', 'click', 'link in bio', 'order now']):
            types['direct_cta'] += 1
        elif any(w in first_line for w in ['stuck', 'struggling', 'tired of', 'feeling']):
            types['empathy'] += 1
        elif any(w in first_line for w in ['✨', '\U0001f319', '\U0001f52e', 'universe', 'energy', 'manifest']):
            types['philosophy'] += 1
        else:
            types['other'] += 1
    total = sum(types.values()) or 1
    return {k: {'count': v, 'pct': round(v / total * 100, 1)} for k, v in types.items() if v > 0}
