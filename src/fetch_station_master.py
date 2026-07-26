"""서울 열린데이터광장에서 공식 대여소 ID·좌표를 내려받는다."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/processed_data/official_station_master.csv"))
    args = parser.parse_args()
    key = os.getenv("SEOUL_OPEN_DATA_API_KEY")
    if not key:
        raise RuntimeError("SEOUL_OPEN_DATA_API_KEY가 설정되지 않았습니다.")
    rows = []
    for start in (1, 1001, 2001):
        end = start + 999
        url = f"http://openapi.seoul.go.kr:8088/{key}/json/bikeList/{start}/{end}/"
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
        block = payload.get("rentBikeStatus", {})
        if block.get("RESULT", {}).get("CODE") != "INFO-000":
            raise RuntimeError(block.get("RESULT", {}).get("MESSAGE", "서울시 API 오류"))
        rows.extend(block.get("row", []))
    fields = ["stationId", "stationName", "stationLatitude", "stationLongitude",
              "rackTotCnt", "parkingBikeTotCnt", "shared"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows if row.get("stationId"))
    print(f"wrote {args.output}: {len(rows)} stations")


if __name__ == "__main__":
    main()

