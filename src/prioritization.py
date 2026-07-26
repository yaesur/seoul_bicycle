"""근거리 불균형 후보의 우선순위와 제한된 사전 배치 시나리오."""
from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Iterable


@dataclass(frozen=True)
class Station:
    name: str
    lat: float
    lng: float
    imbalance: int


def haversine(a: Station, b: Station) -> float:
    dlat = radians(b.lat - a.lat)
    dlng = radians(b.lng - a.lng)
    x = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlng / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(x))


@dataclass(frozen=True)
class Candidate:
    source: Station
    target: Station
    matchable: int
    distance_km: float
    score: float


def rank_candidates(stations: Iterable[Station], max_distance_km: float = 5) -> list[Candidate]:
    stations = list(stations)
    surplus = [s for s in stations if s.imbalance > 0]
    shortage = [s for s in stations if s.imbalance < 0]
    result = []
    for source in surplus:
        for target in shortage:
            distance = haversine(source, target)
            if not 0.1 <= distance <= max_distance_km:
                continue
            matchable = min(source.imbalance, -target.imbalance)
            score = matchable * sqrt(source.imbalance * -target.imbalance) / (distance + 0.5)
            result.append(Candidate(source, target, matchable, distance, score))
    return sorted(result, key=lambda x: (-x.score, x.distance_km, x.source.name, x.target.name))


def allocate_by_priority(stations: Iterable[Station], candidates: Iterable[Candidate], budget: int):
    stations = list(stations)
    supply = {s.name: s.imbalance for s in stations if s.imbalance > 0}
    demand = {s.name: -s.imbalance for s in stations if s.imbalance < 0}
    orders = []
    for candidate in candidates:
        if budget <= 0:
            break
        amount = min(supply.get(candidate.source.name, 0), demand.get(candidate.target.name, 0), budget)
        if amount <= 0:
            continue
        orders.append((candidate, amount))
        supply[candidate.source.name] -= amount
        demand[candidate.target.name] -= amount
        budget -= amount
    return orders
