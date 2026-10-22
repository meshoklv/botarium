#!/usr/bin/env python3
"""
Health Monitor - Morning health report pipeline.

Usage:
    python3 main.py              # Full pipeline: fetch from phone -> parse -> analyze -> notify
    python3 main.py --demo       # Demo mode: generate fake data -> analyze -> notify
    python3 main.py --local      # Use already fetched local DB
    python3 main.py --json FILE  # Use pre-made JSON data file
    python3 main.py --dry-run    # Analyze but don't send to Telegram
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime

import config
from fetch_data import fetch_from_phone, fetch_from_local, generate_demo_data
from parse_gadgetbridge import parse_db, save_parsed_data
from analyze import analyze
from notify import send_telegram


def main():
    parser = argparse.ArgumentParser(description="Health Monitor - Morning Report")
    parser.add_argument("--demo", action="store_true", help="Use demo data")
    parser.add_argument("--local", action="store_true", help="Use local DB file")
    parser.add_argument("--json", type=str, help="Use pre-made JSON data file")
    parser.add_argument("--dry-run", action="store_true", help="Don't send to Telegram")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD), default=yesterday")
    parser.add_argument("--cli", action="store_true", help="Use the Claude CLI (default unless ANALYZER=api)")
    parser.add_argument("--api", action="store_true", help="Use Claude API instead of CLI")
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Health Monitor starting...")

    try:
        # Step 1: Get data
        if args.json:
            print(f"Loading JSON data from {args.json}")
            with open(args.json) as f:
                health_data = json.load(f)
        elif args.demo:
            print("Generating demo data...")
            health_data = generate_demo_data()
        else:
            # Fetch DB from phone or use local
            if args.local:
                db_path = fetch_from_local()
            else:
                print("Fetching DB from phone...")
                db_path = fetch_from_phone()
                if not db_path:
                    print("Phone fetch failed, trying local DB...")
                    db_path = fetch_from_local()

            if not db_path:
                error_msg = "Could not get Gadgetbridge database. Phone not reachable and no local copy."
                print(error_msg)
                if not args.dry_run:
                    send_telegram(f"Health Monitor error: {error_msg}")
                return 1

            # Step 2: Parse
            print(f"Parsing DB: {db_path}")
            health_data = parse_db(db_path, target_date=args.date)
            save_parsed_data(health_data)

        # Step 3: Analyze with Claude
        print("Sending to Claude for analysis...")
        report = analyze(health_data, use_api=args.api)

        print(f"\n{'='*50}")
        print("REPORT:")
        print(f"{'='*50}")
        print(report)
        print(f"{'='*50}\n")

        # Step 4: Send to Telegram
        if args.dry_run:
            print("[DRY RUN] Report not sent to Telegram")
        else:
            header = f"**Health Report | {health_data.get('date', 'today')}**\n\n"
            send_telegram(header + report)
            print("Report sent to Telegram!")

        return 0

    except Exception as e:
        error_msg = f"Health Monitor error: {e}\n{traceback.format_exc()}"
        print(error_msg)
        if not args.dry_run:
            send_telegram(f"Health Monitor error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
