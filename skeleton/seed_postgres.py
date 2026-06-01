"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import os
import bcrypt
import sys
from datetime import date, datetime, time

import psycopg2
from psycopg2.extras import Json, execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount

def _split_full_name(full_name):
    parts = str(full_name).strip().split(None, 1)
    first_name = parts[0] if parts else ""
    surname = parts[1] if len(parts) > 1 else ""
    return first_name, surname


def _parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _parse_time(value):
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    station_rows = []
    adjacent_rows = []

    for item in data:
        station_rows.append(
            (
                item["station_id"],
                item["name"],
                item["is_interchange_metro"],
                item["is_interchange_national_rail"],
                item["interchange_national_rail_station_id"],
            )
        )

        for adjacent in item.get("adjacent_stations", []):
            adjacent_rows.append(
                (
                    item["station_id"],
                    adjacent["station_id"],
                    adjacent["line"],
                    adjacent["travel_time_min"],
                )
            )

    insert_many(
        cur,
        "metro_stations",
        [
            "station_id",
            "name",
            "is_interchange_metro",
            "is_interchange_national_rail",
            "interchange_national_rail_station_id",
        ],
        station_rows,
    )
    insert_many(
        cur,
        "metro_station_adjacent_stations",
        ["station_id", "adjacent_station_id", "line", "travel_time_min"],
        adjacent_rows,
    )


def seed_metro_station_lines(cur):
    data = load("metro_stations.json")
    line_rows = []

    for item in data:
        for line in item.get("lines", []):
            line_rows.append((item["station_id"], line))

    insert_many(cur, "metro_station_lines", ["station_id", "line"], line_rows)


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    station_rows = [
        (
            item["station_id"],
            item["name"],
            item["is_interchange_national_rail"],
            item["is_interchange_metro"],
            item["interchange_metro_station_id"],
        )
        for item in data
    ]
    line_rows = [
        (item["station_id"], line)
        for item in data
        for line in item.get("lines", [])
    ]
    adjacent_rows = [
        (
            item["station_id"],
            adjacent["station_id"],
            adjacent["line"],
            adjacent["travel_time_min"],
        )
        for item in data
        for adjacent in item.get("adjacent_stations", [])
    ]

    insert_many(
        cur,
        "national_rail_stations",
        [
            "station_id",
            "name",
            "is_interchange_national_rail",
            "is_interchange_metro",
            "interchange_metro_station_id",
        ],
        station_rows,
    )
    insert_many(
        cur,
        "national_rail_station_lines",
        ["station_id", "line"],
        line_rows,
    )
    insert_many(
        cur,
        "national_rail_station_adjacent_stations",
        ["station_id", "adjacent_station_id", "line", "travel_time_min"],
        adjacent_rows,
    )


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    schedule_rows = []
    stop_rows = []
    operating_rows = []

    for item in data:
        schedule_rows.append(
            (
                item["schedule_id"],
                item["line"],
                item["direction"],
                item["origin_station_id"],
                item["destination_station_id"],
                item["first_train_time"],
                item["last_train_time"],
                item["base_fare_usd"],
                item["per_stop_rate_usd"],
                item["frequency_min"],
            )
        )

        for stop_order, station_id in enumerate(item.get("stops_in_order", []), start=1):
            stop_rows.append(
                (
                    item["schedule_id"],
                    stop_order,
                    station_id,
                    item["travel_time_from_origin_min"][station_id],
                )
            )

        for day_of_week in item.get("operates_on", []):
            operating_rows.append((item["schedule_id"], day_of_week))

    insert_many(
        cur,
        "metro_schedules",
        [
            "schedule_id",
            "line",
            "direction",
            "origin_station_id",
            "destination_station_id",
            "first_train_time",
            "last_train_time",
            "base_fare_usd",
            "per_stop_rate_usd",
            "frequency_min",
        ],
        schedule_rows,
    )
    insert_many(
        cur,
        "metro_schedule_stops",
        [
            "schedule_id",
            "stop_order",
            "station_id",
            "travel_time_from_origin_min",
        ],
        stop_rows,
    )
    insert_many(
        cur,
        "metro_schedule_operating_days",
        ["schedule_id", "day_of_week"],
        operating_rows,
    )


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    schedule_rows = []
    stop_rows = []
    passed_rows = []
    fare_rows = []
    operating_rows = []

    for item in data:
        schedule_rows.append(
            (
                item["schedule_id"],
                item["line"],
                item["service_type"],
                item["direction"],
                item["origin_station_id"],
                item["destination_station_id"],
                item["first_train_time"],
                item["last_train_time"],
                item["frequency_min"],
            )
        )

        for stop_order, station_id in enumerate(item.get("stops_in_order", []), start=1):
            stop_rows.append(
                (
                    item["schedule_id"],
                    stop_order,
                    station_id,
                    item["travel_time_from_origin_min"][station_id],
                )
            )

        for station_id in item.get("passed_through_stations", []):
            passed_rows.append((item["schedule_id"], station_id))

        for fare_class, fare_data in item.get("fare_classes", {}).items():
            fare_rows.append(
                (
                    item["schedule_id"],
                    fare_class,
                    fare_data["base_fare_usd"],
                    fare_data["per_stop_rate_usd"],
                )
            )

        for day_of_week in item.get("operates_on", []):
            operating_rows.append((item["schedule_id"], day_of_week))

    insert_many(
        cur,
        "national_rail_schedules",
        [
            "schedule_id",
            "line",
            "service_type",
            "direction",
            "origin_station_id",
            "destination_station_id",
            "first_train_time",
            "last_train_time",
            "frequency_min",
        ],
        schedule_rows,
    )
    insert_many(
        cur,
        "national_rail_schedule_stops",
        [
            "schedule_id",
            "stop_order",
            "station_id",
            "travel_time_from_origin_min",
        ],
        stop_rows,
    )
    insert_many(
        cur,
        "national_rail_schedule_passed_through_stations",
        ["schedule_id", "station_id"],
        passed_rows,
    )
    insert_many(
        cur,
        "national_rail_schedule_fares",
        ["schedule_id", "fare_class", "base_fare_usd", "per_stop_rate_usd"],
        fare_rows,
    )
    insert_many(
        cur,
        "national_rail_schedule_operating_days",
        ["schedule_id", "day_of_week"],
        operating_rows,
    )


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    layout_rows = []
    coach_rows = []
    seat_rows = []

    for item in data:
        layout_rows.append((item["layout_id"], item["schedule_id"]))

        for coach in item.get("coaches", []):
            coach_rows.append(
                (
                    item["schedule_id"],
                    coach["coach"],
                    item["layout_id"],
                    coach["fare_class"],
                )
            )

            for seat in coach.get("seats", []):
                seat_rows.append(
                    (
                        item["schedule_id"],
                        coach["coach"],
                        seat["seat_id"],
                        seat["row"],
                        seat["column"],
                    )
                )

    insert_many(
        cur,
        "national_rail_seat_layouts",
        ["layout_id", "schedule_id"],
        layout_rows,
    )
    insert_many(
        cur,
        "national_rail_coaches",
        ["schedule_id", "coach", "layout_id", "fare_class"],
        coach_rows,
    )
    insert_many(
        cur,
        "national_rail_seats",
        ["schedule_id", "coach", "seat_id", "row_number", "seat_column"],
        seat_rows,
    )


def seed_national_rail_seat_layouts(cur):
    seed_seat_layouts(cur)


def seed_users(cursor):
    file_path = os.path.join("train-mock-data", "registered_users.json")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"  -> 準備載入 {len(data)} 筆使用者資料 (採用高資安三表架構與密碼雜湊)...")

    users_rows = []
    passwords_rows = []
    questions_rows = []

    for u in data:
        # 1. 基礎個資
        users_rows.append((
            u["user_id"],
            u["email"],
            u["full_name"],
            u["phone"],
            u["date_of_birth"],
            u.get("is_active", True),
            u["registered_at"],
        ))

        # 2. 密碼與 Salt 處理
        # 動態生成隨機 salt，rounds=12 是目前標準的安全性設定
        salt = bcrypt.gensalt(rounds=12)
        # 結合原密碼與 salt 進行雜湊
        hashed_password = bcrypt.hashpw(u["password"].encode('utf-8'), salt)

        # 由於 bcrypt 處理後會是 bytes 型態，寫入資料庫前需 decode 轉回字串
        passwords_rows.append((
            u["user_id"],
            hashed_password.decode('utf-8'),
            salt.decode('utf-8')
        ))

        # 3. 安全提示問答
        questions_rows.append((
            u["user_id"],
            u["secret_question"],
            u["secret_answer"]
        ))

    # 依序寫入三張表
    insert_many(cursor, "users", ["user_id", "email", "full_name", "phone", "date_of_birth", "is_active", "registered_at"], users_rows)
    insert_many(cursor, "user_passwords", ["user_id", "password", "salt"], passwords_rows)
    insert_many(cursor, "user_security_questions", ["user_id", "secret_question", "secret_answer"], questions_rows)

    print(f"  -> 成功寫入 {len(users_rows)} 筆使用者資料及其雜湊驗證資訊！")


def seed_ticket_types(cur):
    data = load("ticket_types.json")
    ticket_rows = []
    network_rows = []
    rule_rows = []

    for item in data:
        ticket_rows.append(
            (
                item["ticket_type"],
                item["display_name"],
                item["description"],
            )
        )

        for network_type in item.get("available_on", []):
            network_rows.append((item["ticket_type"], network_type))
            if network_type in item:
                rule_rows.append((item["ticket_type"], network_type, Json(item[network_type])))

    insert_many(cur, "ticket_types", ["ticket_type", "display_name", "description"], ticket_rows)
    insert_many(cur, "ticket_type_networks", ["ticket_type", "network_type"], network_rows)
    insert_many(cur, "ticket_type_rules", ["ticket_type", "network_type", "rules"], rule_rows)


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = [
        (
            item["booking_id"],
            item["user_id"],
            item["schedule_id"],
            item["origin_station_id"],
            item["destination_station_id"],
            _parse_date(item["travel_date"]),
            _parse_time(item["departure_time"]),
            item["ticket_type"],
            item["fare_class"],
            item["coach"],
            item["seat_id"],
            item["stops_travelled"],
            item["amount_usd"],
            item["status"],
            _parse_timestamp(item["booked_at"]),
            _parse_timestamp(item.get("travelled_at")),
        )
        for item in data
    ]

    insert_many(
        cur,
        "bookings",
        [
            "booking_id",
            "user_id",
            "schedule_id",
            "origin_station_id",
            "destination_station_id",
            "travel_date",
            "departure_time",
            "ticket_type",
            "fare_class",
            "coach",
            "seat_id",
            "stops_travelled",
            "amount_usd",
            "status",
            "booked_at",
            "travelled_at",
        ],
        rows,
    )


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    rows = [
        (
            item["trip_id"],
            item["user_id"],
            item["schedule_id"],
            item["origin_station_id"],
            item["destination_station_id"],
            _parse_date(item["travel_date"]),
            item["ticket_type"],
            item.get("day_pass_ref"),
            item.get("stops_travelled"),
            item["amount_usd"],
            item["status"],
            _parse_timestamp(item.get("purchased_at")),
            _parse_timestamp(item.get("travelled_at")),
        )
        for item in data
    ]

    insert_many(
        cur,
        "metro_travel_history",
        [
            "trip_id",
            "user_id",
            "schedule_id",
            "origin_station_id",
            "destination_station_id",
            "travel_date",
            "ticket_type",
            "day_pass_ref",
            "stops_travelled",
            "amount_usd",
            "status",
            "purchased_at",
            "travelled_at",
        ],
        rows,
    )


def seed_payments(cur):
    data = load("payments.json")
    rows = [
        (
            item["payment_id"],
            item["booking_id"],
            item["amount_usd"],
            item["method"],
            item["status"],
            _parse_timestamp(item["paid_at"]),
        )
        for item in data
    ]

    insert_many(
        cur,
        "payments",
        ["payment_id", "transaction_ref", "amount_usd", "method", "status", "paid_at"],
        rows,
    )


def seed_feedback(cur):
    data = load("feedback.json")
    rows = [
        (
            item["feedback_id"],
            item["booking_id"],
            item["user_id"],
            item["rating"],
            item.get("comment"),
            _parse_timestamp(item["submitted_at"]),
        )
        for item in data
    ]

    insert_many(
        cur,
        "feedback",
        ["feedback_id", "transaction_ref", "user_id", "rating", "comment", "submitted_at"],
        rows,
    )


def seed_refund_policies(cur):
    data = load("refund_policy.json")
    policy_rows = []
    ticket_rows = []
    window_rows = []

    for item in data:
        applies_to = item.get("applies_to", {})
        policy_rows.append(
            (
                item["policy_id"],
                item["label"],
                applies_to.get("network_type"),
                applies_to.get("service_type"),
                item.get("return_ticket_notes"),
                item.get("no_show_policy"),
                item.get("notes"),
                item.get("exclusions"),
            )
        )
        for ticket_type in applies_to.get("ticket_types", []):
            ticket_rows.append((item["policy_id"], ticket_type))
        for window in item.get("cancellation_windows", []):
            window_rows.append(
                (
                    window["window_id"],
                    item["policy_id"],
                    window["label"],
                    window["condition"],
                    window.get("hours_before_departure_min"),
                    window.get("hours_before_departure_max"),
                    window["refund_percent"],
                    window["admin_fee_usd"],
                )
            )

    insert_many(
        cur,
        "refund_policies",
        [
            "policy_id",
            "label",
            "network_type",
            "service_type",
            "return_ticket_notes",
            "no_show_policy",
            "notes",
            "exclusions",
        ],
        policy_rows,
    )
    insert_many(
        cur,
        "refund_policy_ticket_types",
        ["policy_id", "ticket_type"],
        ticket_rows,
    )
    insert_many(
        cur,
        "refund_policy_cancellation_windows",
        [
            "window_id",
            "policy_id",
            "label",
            "condition",
            "hours_before_departure_min",
            "hours_before_departure_max",
            "refund_percent",
            "admin_fee_usd",
        ],
        window_rows,
    )


def seed_bookings(cur):
    seed_national_rail_bookings(cur)


def seed_metro_travel_history(cur):
    seed_metro_travels(cur)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_users(cur)
        seed_ticket_types(cur)
        seed_metro_stations(cur)
        seed_metro_station_lines(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_seat_layouts(cur)
        seed_refund_policies(cur)
        seed_bookings(cur)
        seed_metro_travel_history(cur)
        seed_payments(cur)
        seed_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
