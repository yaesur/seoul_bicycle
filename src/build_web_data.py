"""대용량 정제 CSV를 청크 집계해 웹 데모용 소형 JSON을 만든다."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd


HOLIDAYS = pd.to_datetime(["2025-05-05", "2025-05-06", "2025-06-03", "2025-06-06"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/processed_data/bicycle_cleaned.csv"))
    parser.add_argument("--locations", type=Path, default=Path("data/processed_data/official_station_master.csv"))
    parser.add_argument("--historical-locations", type=Path, default=Path("data/processed_data/station_master_2025_06.xlsx"))
    parser.add_argument("--output", type=Path, default=Path("data/processed_data/simulation_data.json"))
    parser.add_argument("--chunksize", type=int, default=750_000)
    parser.add_argument("--top-n", type=int, default=0, help="0이면 조건을 만족하는 전체 대여소")
    parser.add_argument("--min-usage", type=int, default=300)
    args = parser.parse_args()

    periods = {
        "morning": (7, 9, "workday"),
        "evening": (17, 20, "workday"),
        "leisure": (12, 18, "leisure"),
    }
    totals = {p: {"rent": defaultdict(int), "return": defaultdict(int)} for p in periods}
    observed_dates = {p: set() for p in periods}
    columns = ["기준_날짜", "시작_대여소_ID", "종료_대여소_ID", "전체_건수", "start_hour"]
    for number, chunk in enumerate(pd.read_csv(args.input, usecols=columns, chunksize=args.chunksize), 1):
        dates = pd.to_datetime(chunk["기준_날짜"].astype(str), format="%Y%m%d", errors="coerce")
        is_leisure = (dates.dt.weekday >= 5) | dates.isin(HOLIDAYS)
        count = pd.to_numeric(chunk["전체_건수"], errors="coerce").fillna(0).astype("int64")
        hours = pd.to_numeric(chunk["start_hour"], errors="coerce")
        for period, (start, end, day_type) in periods.items():
            day_mask = ~is_leisure if day_type == "workday" else is_leisure
            mask = hours.between(start, end) & day_mask
            observed_dates[period].update(dates.loc[mask].dropna().dt.strftime("%Y-%m-%d").unique())
            part = chunk.loc[mask].copy()
            part["전체_건수"] = count.loc[part.index]
            for station_id, value in part.groupby("시작_대여소_ID", observed=True)["전체_건수"].sum().items():
                totals[period]["rent"][station_id] += int(value)
            for station_id, value in part.groupby("종료_대여소_ID", observed=True)["전체_건수"].sum().items():
                totals[period]["return"][station_id] += int(value)
        print(f"processed chunk {number}", flush=True)

    locations = pd.read_csv(args.locations)
    locations = locations.rename(columns={"stationId": "대여소_ID", "stationName": "대여소명",
                                          "stationLatitude": "위도", "stationLongitude": "경도",
                                          "rackTotCnt": "거치대수", "parkingBikeTotCnt": "현재자전거수"})
    locations["위도"] = pd.to_numeric(locations["위도"], errors="coerce")
    locations["경도"] = pd.to_numeric(locations["경도"], errors="coerce")
    locations["대여소번호"] = pd.to_numeric(locations["대여소명"].astype(str).str.extract(r"^\s*(\d+)")[0], errors="coerce")
    if args.historical_locations.exists():
        historical = pd.read_excel(args.historical_locations, header=None, skiprows=5, usecols=range(6))
        historical.columns = ["대여소번호", "과거대여소명", "자치구", "상세주소", "과거위도", "과거경도"]
        historical["대여소번호"] = pd.to_numeric(historical["대여소번호"], errors="coerce")
        historical = historical.dropna(subset=["대여소번호"]).drop_duplicates("대여소번호")
        locations = locations.merge(historical[["대여소번호", "자치구", "상세주소"]], on="대여소번호", how="left")
    else:
        locations["자치구"], locations["상세주소"] = "", ""
    locations = locations.dropna(subset=["대여소_ID", "위도", "경도"]).drop_duplicates("대여소_ID")
    location_map = locations.set_index("대여소_ID")[["대여소명", "위도", "경도", "거치대수", "현재자전거수", "자치구", "상세주소"]].to_dict("index")
    result = {"metadata": {"unit": "representative_day_flow_proxy", "period_days": {},
                           "coordinate_source_rows": len(locations), "geocoded_station_count": len(location_map)}, "periods": {}}
    for period, values in totals.items():
        days = max(1, len(observed_dates[period]))
        result["metadata"]["period_days"][period] = days
        rows, unmapped = [], []
        for station_id in set(values["rent"]) | set(values["return"]):
            rent, returned = values["rent"][station_id], values["return"][station_id]
            usage = rent + returned
            if usage < args.min_usage:
                continue
            cumulative_imbalance = returned - rent
            imbalance = round(cumulative_imbalance / days)
            if imbalance == 0:
                continue
            if station_id not in location_map:
                unmapped.append({"station_id": station_id, "name": station_id, "rent": rent, "return": returned,
                                 "imbalance": imbalance, "cumulative_imbalance": cumulative_imbalance,
                                 "imbalance_idx": cumulative_imbalance / usage})
                continue
            loc = location_map[station_id]
            rows.append({"station_id": station_id, "name": str(loc["대여소명"]), "lat": float(loc["위도"]), "lng": float(loc["경도"]),
                         "district": "" if pd.isna(loc["자치구"]) else str(loc["자치구"]),
                         "address": station_id if pd.isna(loc["상세주소"]) else str(loc["상세주소"]), "capacity": int(float(loc["거치대수"] or 0)),
                         "current_bikes": int(float(loc["현재자전거수"] or 0)), "rent": rent, "return": returned,
                         "imbalance": imbalance, "cumulative_imbalance": cumulative_imbalance,
                         "imbalance_idx": cumulative_imbalance / usage})
        surplus = sorted((r for r in rows if r["imbalance"] > 0), key=lambda r: -r["imbalance"])
        shortage = sorted((r for r in rows if r["imbalance"] < 0), key=lambda r: r["imbalance"])
        if args.top_n > 0:
            surplus, shortage = surplus[:args.top_n], shortage[:args.top_n]
        result["periods"][period] = {
            "surplus": surplus,
            "shortage": shortage,
            "unmapped": sorted(unmapped, key=lambda r: -abs(r["imbalance"])),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
