"""Generate candidate rotations and apply the farmer's constraints."""
import itertools

MAIN_CROPS = ["corn", "soybean", "winter_wheat"]     # crops simulated by the water model
COVER_CROPS = ["cereal_rye", "red_clover"]           # no water model (no library data): rule-based ratings only


def _canonical(seq):
    """Cyclic shifts of a rotation are the same rotation; return the smallest representation."""
    return min(tuple(seq[i:] + seq[:i]) for i in range(len(seq)))


def _is_repeat_of_shorter(seq):
    n = len(seq)
    return any(n % k == 0 and seq == seq[:k] * (n // k) for k in range(1, n))


def main_sequences(rules, lengths=(2, 3, 4)):
    """All distinct cyclic main-crop sequences that avoid disallowed successions."""
    banned = {(d["from"], d["to"]) for d in rules["disallowed_successions"]}
    seen = set()
    for n in lengths:
        for seq in itertools.product(MAIN_CROPS, repeat=n):
            seq = list(seq)
            if _is_repeat_of_shorter(seq):
                continue
            if any((seq[i - 1], seq[i]) in banned for i in range(n)):
                continue
            seen.add(_canonical(seq))
    return sorted(seen, key=lambda s: (len(s), s))


def cover_variants(seq):
    """Rotations built from one main sequence: no cover, rye everywhere it fits, clover under
    wheat, and both. Duplicates removed."""
    def build(rye, clover):
        years = []
        for crop in seq:
            cover = None
            if crop == "winter_wheat" and clover:
                cover = "red_clover"
            elif rye and not (crop == "winter_wheat" and clover):
                cover = "cereal_rye"
            years.append((crop, cover))
        return tuple(years)

    out = []
    for rye, clover in [(False, False), (True, False), (False, True), (True, True)]:
        if clover and "winter_wheat" not in seq:
            continue
        rot = build(rye, clover)
        if rot not in out:
            out.append(rot)
    return out


def all_candidates(rules):
    return [rot for seq in main_sequences(rules) for rot in cover_variants(list(seq))]


def crops_in(rotation):
    return {c for year in rotation for c in year if c}


def equipment_needed(rotation, crops):
    need = set()
    for c in crops_in(rotation):
        need.update(crops[c].get("needs_equipment", []))
    return need


def filter_candidates(candidates, crops, must_include=(), avoid=(), equipment=None):
    """Apply hard constraints. equipment=None means 'assume everything is available'."""
    out = []
    for rot in candidates:
        used = crops_in(rot)
        if any(m not in used for m in must_include) or any(a in used for a in avoid):
            continue
        if equipment is not None and not equipment_needed(rot, crops) <= set(equipment):
            continue
        out.append(rot)
    return out


def canonical_rotation(rotation):
    """Cyclic-shift-invariant key for a rotation (used to avoid recommending the baseline)."""
    seq = [tuple(y) for y in rotation]
    return min(tuple(seq[i:] + seq[:i]) for i in range(len(seq)))
