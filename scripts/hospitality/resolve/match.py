"""Rule-based matching of SLA license records to DOHMH inspection venues."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from rapidfuzz import fuzz

from scripts.hospitality.config import HospitalityConfig
from scripts.hospitality.models import (
    EntityLink,
    InspectionVenue,
    LicenseRecord,
    MatchPair,
    MatchResult,
)
from scripts.hospitality.resolve.normalize import (
    haversine_m,
    normalize_address,
    normalize_name,
)

_LOCATION_WEIGHT = 0.6
_NAME_WEIGHT = 0.4


def _score(
    lic: LicenseRecord,
    ins: InspectionVenue,
    max_distance_m: float,
    lic_addr: str,
    ins_addr: str,
    lic_names: tuple[str, str],
    ins_name: str,
) -> tuple[float, str]:
    """Score a pair from pre-normalized fields (normalization dominates cost at scale)."""
    if lic_addr == ins_addr:
        location, loc_method = 1.0, "address"
    elif None not in (lic.lat, lic.lon, ins.lat, ins.lon):
        dist = haversine_m(lic.lat, lic.lon, ins.lat, ins.lon)  # type: ignore[arg-type]
        location, loc_method = max(0.0, 1.0 - dist / max_distance_m), "geo"
    else:
        location, loc_method = 0.0, "name_only"
    name = max(fuzz.token_set_ratio(n, ins_name) for n in lic_names) / 100.0
    p = _LOCATION_WEIGHT * location + _NAME_WEIGHT * name
    return p, "name_only" if loc_method == "name_only" else f"{loc_method}+name"


def pair_probability(
    lic: LicenseRecord, ins: InspectionVenue, max_distance_m: float
) -> tuple[float, str]:
    """Score one license/inspection pair on location and name; return (p, method)."""
    return _score(
        lic,
        ins,
        max_distance_m,
        normalize_address(lic.address),
        normalize_address(ins.address),
        (normalize_name(lic.dba), normalize_name(lic.legal_name)),
        normalize_name(ins.dba),
    )


def match_licenses(
    licenses: Sequence[LicenseRecord],
    inspections: Sequence[InspectionVenue],
    cfg: HospitalityConfig,
) -> MatchResult:
    """Match each license to its best inspection venue within the same ZIP block."""
    by_zip: dict[str, list[tuple[InspectionVenue, str, str]]] = defaultdict(list)
    for ins in inspections:
        by_zip[ins.zip_code.strip()[:5]].append(
            (ins, normalize_address(ins.address), normalize_name(ins.dba))
        )

    pairs: list[MatchPair] = []
    links: list[EntityLink] = []
    unmatched_licenses: list[str] = []
    matched_camis: set[str] = set()
    for lic in licenses:
        best: tuple[float, str, str] | None = None
        lic_addr = normalize_address(lic.address)
        lic_names = (normalize_name(lic.dba), normalize_name(lic.legal_name))
        for ins, ins_addr, ins_name in by_zip.get(lic.zip_code.strip()[:5], ()):
            p, method = _score(
                lic, ins, cfg.match_max_distance_m, lic_addr, ins_addr, lic_names, ins_name
            )
            if best is None or p > best[0] or (p == best[0] and ins.camis < best[2]):
                best = (p, method, ins.camis)
        if best is not None and best[0] >= cfg.match_auto_threshold:
            pairs.append(
                MatchPair(
                    license_id=lic.record_id, camis=best[2], probability=best[0], method=best[1]
                )
            )
            matched_camis.add(best[2])
        elif best is not None and best[0] >= cfg.match_link_threshold:
            links.append(
                EntityLink(
                    left_id=lic.record_id,
                    right_id=best[2],
                    kind="possibly_same",
                    probability=best[0],
                    method=best[1],
                )
            )
        else:
            unmatched_licenses.append(lic.record_id)
    unmatched_camis = sorted({i.camis for i in inspections} - matched_camis)
    return MatchResult(
        pairs=tuple(pairs),
        links=tuple(links),
        unmatched_licenses=tuple(unmatched_licenses),
        unmatched_camis=tuple(unmatched_camis),
    )
