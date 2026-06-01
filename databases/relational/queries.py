from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD
import random
import string
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import psycopg2
import psycopg2.extras

def _connect():
    """Return a new psycopg2 connection with autocommit enabled."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn
def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"
def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"
#user profile
def query_user_profile(user_email: str) -> Optional[dict]:
    """
    Return a user's profile by email.

    Args:
        user_email: user's email address

    Returns:
        User profile dictionary or None if not found
    """
    sql = """
        SELECT
            user_id,
            email,
            first_name,
            surname,
            full_name,
            phone,
            date_of_birth,
            is_active,
            registered_at
        FROM users
        WHERE email = %s
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()

            if row is None:
                return None

            return dict(row)
#login user
def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials.

    Args:
        email: user email
        password: user password

    Returns:
        User dictionary on success, None on failure.
    """
    sql = """
        SELECT
            user_id,
            email,
            full_name,
            first_name,
            surname,
            phone,
            date_of_birth,
            is_active
        FROM users
        WHERE email = %s
          AND password = %s
          AND is_active = TRUE
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (email, password))
            row = cur.fetchone()

            if row is None:
                return None

            return dict(row)
#user secret question
def get_user_secret_question(email: str) -> Optional[str]:
    """
    Return the secret question for a registered email,
    or None if the email does not exist.

    Args:
        email: user email address

    Returns:
        Secret question string or None
    """
    sql = """
        SELECT secret_question
        FROM users
        WHERE email = %s
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()

            if row is None:
                return None

            return row[0]
#verify user secret answer
def verify_secret_answer(email: str, answer: str) -> bool:
    """
    Return True if the provided answer matches the stored
    secret answer (case-insensitive).

    Args:
        email: user email address
        answer: answer provided by user

    Returns:
        True if answer matches, otherwise False
    """
    sql = """
        SELECT secret_answer
        FROM users
        WHERE email = %s
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()

            if row is None:
                return False

            stored_answer = row[0]

            return (
                stored_answer.strip().lower()
                == answer.strip().lower()
            )
#update user password
def update_password(email: str, new_password: str) -> bool:
    """
    Update the password for a user.

    Args:
        email: user email address
        new_password: new password

    Returns:
        True if updated successfully, False otherwise.
    """
    sql = """
        UPDATE users
        SET password = %s
        WHERE email = %s
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new_password, email))

            return cur.rowcount > 0
#metro fare calculation
def query_metro_fare(
    schedule_id: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the metro fare for a single-ticket journey.

    Args:
        schedule_id: e.g. "MS_SCH01"
        stops_travelled: number of stops between origin and destination

    Returns:
        dict with base_fare_usd, per_stop_rate_usd, total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            base_fare_usd,
            per_stop_rate_usd
        FROM metro_schedules
        WHERE schedule_id = %s
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()

            if row is None:
                return None

            result = dict(row)

            total_fare = (
                float(result["base_fare_usd"])
                + float(result["per_stop_rate_usd"]) * stops_travelled
            )

            result["stops_travelled"] = stops_travelled
            result["total_fare_usd"] = round(total_fare, 2)

            return result
#national rail fare calculation
def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    """
    Calculate the fare for a national rail journey.

    Args:
        schedule_id: e.g. "NR_SCH01"
        fare_class: "standard" or "first"
        stops_travelled: number of stops travelled

    Returns:
        dict with fare_class, base_fare_usd,
        per_stop_rate_usd and total_fare_usd
    """
    sql = """
        SELECT
            schedule_id,
            fare_class,
            base_fare_usd,
            per_stop_rate_usd
        FROM national_rail_schedule_fares
        WHERE schedule_id = %s
          AND fare_class = %s
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                sql,
                (schedule_id, fare_class)
            )

            row = cur.fetchone()

            if row is None:
                return None

            result = dict(row)

            total_fare = (
                float(result["base_fare_usd"])
                + float(result["per_stop_rate_usd"]) * stops_travelled
            )

            result["stops_travelled"] = stops_travelled
            result["total_fare_usd"] = round(total_fare, 2)

            return result
#available seats query
def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Return available seats for a national rail journey on a given date.

    Args:
        schedule_id: e.g. "NR_SCH01"
        travel_date: e.g. "2025-06-01"
        fare_class: "standard" or "first"

    Returns:
        List of dicts: {seat_id, coach, row, column}
    """
    sql = """
        SELECT
            s.seat_id,
            s.coach,
            s.row_number AS row,
            s.seat_column AS column
        FROM national_rail_seats s
        JOIN national_rail_coaches c
            ON c.schedule_id = s.schedule_id
           AND c.coach = s.coach
        LEFT JOIN bookings b
            ON b.schedule_id = s.schedule_id
           AND b.coach = s.coach
           AND b.seat_id = s.seat_id
           AND b.travel_date = %s
           AND b.status <> 'cancelled'
        WHERE s.schedule_id = %s
          AND c.fare_class = %s
          AND b.booking_id IS NULL
        ORDER BY
            s.coach,
            s.row_number,
            s.seat_column
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                sql,
                (travel_date, schedule_id, fare_class)
            )
            return [dict(row) for row in cur.fetchall()]
#metro schedules query
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination
    in the correct order.

    Args:
        origin_id: e.g. "MS01"
        destination_id: e.g. "MS09"

    Returns:
        List of matching metro schedules.
    """
    sql = """
        SELECT
            ms.schedule_id,
            ms.line,
            ms.direction,
            os.station_id AS origin_station_id,
            origin_station.name AS origin_name,
            ds.station_id AS destination_station_id,
            destination_station.name AS destination_name,
            ms.first_train_time::text,
            ms.last_train_time::text,
            ms.frequency_min,
            os.stop_order AS origin_stop_order,
            ds.stop_order AS destination_stop_order,
            ds.stop_order - os.stop_order AS stops_travelled,
            ds.travel_time_from_origin_min
                - os.travel_time_from_origin_min AS travel_time_min
        FROM metro_schedules ms
        JOIN metro_schedule_stops os
            ON os.schedule_id = ms.schedule_id
           AND os.station_id = %s
        JOIN metro_schedule_stops ds
            ON ds.schedule_id = ms.schedule_id
           AND ds.station_id = %s
        JOIN metro_stations origin_station
            ON origin_station.station_id = os.station_id
        JOIN metro_stations destination_station
            ON destination_station.station_id = ds.station_id
        WHERE os.stop_order < ds.stop_order
        ORDER BY
            ms.line,
            ms.direction,
            ms.first_train_time
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (origin_id, destination_id))
            return [dict(row) for row in cur.fetchall()]
#national rail schedules query
def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
) -> list[dict]:
    """
    Return national rail schedules that serve both origin and destination stations
    in the correct order, along with seat occupancy for the requested travel date.

    Args:
        origin_id: e.g. "NR01"
        destination_id: e.g. "NR05"
        travel_date: e.g. "2025-06-01" — used to count bookings; omit for general info

    Returns:
        List of matching national rail schedules with seat occupancy.
    """
    sql = """
        SELECT
            nrs.schedule_id,
            nrs.line,
            nrs.service_type,
            nrs.direction,
            os.station_id AS origin_station_id,
            origin_station.name AS origin_name,
            ds.station_id AS destination_station_id,
            destination_station.name AS destination_name,
            nrs.first_train_time::text AS first_train_time,
            nrs.last_train_time::text AS last_train_time,
            nrs.frequency_min,

            os.stop_order AS origin_stop_order,
            ds.stop_order AS destination_stop_order,
            ds.stop_order - os.stop_order AS stops_travelled,

            ds.travel_time_from_origin_min
                - os.travel_time_from_origin_min AS travel_time_min,

            COUNT(DISTINCT (seat.coach, seat.seat_id)) AS total_seats,

            COUNT(DISTINCT b.booking_id) AS booked_seats,

            COUNT(DISTINCT (seat.coach, seat.seat_id))
                - COUNT(DISTINCT b.booking_id) AS available_seats

        FROM national_rail_schedules nrs

        JOIN national_rail_schedule_stops os
            ON os.schedule_id = nrs.schedule_id
           AND os.station_id = %s

        JOIN national_rail_schedule_stops ds
            ON ds.schedule_id = nrs.schedule_id
           AND ds.station_id = %s

        JOIN national_rail_stations origin_station
            ON origin_station.station_id = os.station_id

        JOIN national_rail_stations destination_station
            ON destination_station.station_id = ds.station_id

        LEFT JOIN national_rail_seats seat
            ON seat.schedule_id = nrs.schedule_id

        LEFT JOIN bookings b
            ON b.schedule_id = nrs.schedule_id
           AND b.travel_date = %s
           AND b.status <> 'cancelled'
           AND b.coach = seat.coach
           AND b.seat_id = seat.seat_id

        WHERE os.stop_order < ds.stop_order

        GROUP BY
            nrs.schedule_id,
            nrs.line,
            nrs.service_type,
            nrs.direction,
            os.station_id,
            origin_station.name,
            ds.station_id,
            destination_station.name,
            nrs.first_train_time,
            nrs.last_train_time,
            nrs.frequency_min,
            os.stop_order,
            ds.stop_order,
            os.travel_time_from_origin_min,
            ds.travel_time_from_origin_min
        ORDER BY
            nrs.line,
            nrs.service_type,
            nrs.first_train_time
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                sql,
                (origin_id, destination_id, travel_date)
            )
            return [dict(row) for row in cur.fetchall()]
#user booking history query
def query_user_bookings(user_email: str) -> dict:
    """
    Return a user's combined booking history.

    Args:
        user_email: user's email address

    Returns:
        dict with keys 'national_rail' and 'metro'
    """
    national_rail_sql = """
        SELECT
            b.booking_id,
            b.travel_date,
            b.departure_time::text AS departure_time,
            b.ticket_type,
            b.fare_class,
            b.coach,
            b.seat_id,
            b.stops_travelled,
            b.amount_usd,
            b.status,
            b.booked_at,
            b.travelled_at,

            nrs.schedule_id,
            nrs.line,
            nrs.service_type,
            nrs.direction,

            orig.station_id AS origin_station_id,
            orig.name AS origin_name,

            dest.station_id AS destination_station_id,
            dest.name AS destination_name

        FROM users u
        JOIN bookings b
            ON b.user_id = u.user_id
        JOIN national_rail_schedules nrs
            ON nrs.schedule_id = b.schedule_id
        JOIN national_rail_stations orig
            ON orig.station_id = b.origin_station_id
        JOIN national_rail_stations dest
            ON dest.station_id = b.destination_station_id

        WHERE u.email = %s

        ORDER BY
            b.travel_date DESC,
            b.departure_time DESC,
            b.booked_at DESC
    """

    metro_sql = """
        SELECT
            mth.trip_id,
            mth.travel_date,
            mth.ticket_type,
            mth.day_pass_ref,
            mth.stops_travelled,
            mth.amount_usd,
            mth.status,
            mth.purchased_at,
            mth.travelled_at,

            ms.schedule_id,
            ms.line,
            ms.direction,

            orig.station_id AS origin_station_id,
            orig.name AS origin_name,

            dest.station_id AS destination_station_id,
            dest.name AS destination_name

        FROM users u
        JOIN metro_travel_history mth
            ON mth.user_id = u.user_id
        JOIN metro_schedules ms
            ON ms.schedule_id = mth.schedule_id
        JOIN metro_stations orig
            ON orig.station_id = mth.origin_station_id
        JOIN metro_stations dest
            ON dest.station_id = mth.destination_station_id

        WHERE u.email = %s

        ORDER BY
            mth.travel_date DESC,
            mth.travelled_at DESC NULLS LAST,
            mth.purchased_at DESC NULLS LAST
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(national_rail_sql, (user_email,))
            national_rail = [dict(row) for row in cur.fetchall()]

            cur.execute(metro_sql, (user_email,))
            metro = [dict(row) for row in cur.fetchall()]

            return {
                "national_rail": national_rail,
                "metro": metro,
            }
#payment info query
def query_payment_info(booking_id: str) -> Optional[dict]:
    """
    Return payment record for a booking or metro trip.

    Args:
        booking_id: booking_id or trip_id, e.g. "BK001" or "MT001"

    Returns:
        Payment dictionary or None if not found.
    """
    sql = """
        SELECT
            payment_id,
            transaction_ref,
            amount_usd,
            method,
            status,
            paid_at
        FROM payments
        WHERE transaction_ref = %s
        ORDER BY paid_at DESC
        LIMIT 1
    """

    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (booking_id,))
            row = cur.fetchone()

            if row is None:
                return None

            return dict(row)
#user registration query
def register_user(
    email: str,
    first_name: str,
    surname: str,
    phone: str,
    date_of_birth: str,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user based on the agreed TransitFlow users schema.

    Args:
        email: User email address.
        first_name: User first name.
        surname: User surname.
        phone: User phone number.
        date_of_birth: User date of birth in YYYY-MM-DD format.
        password: Plain text password for teaching purposes.
        secret_question: Password recovery question.
        secret_answer: Password recovery answer.

    Returns:
        (True, user_id) on success.
        (False, error_message) on failure.
    """
    email = email.strip().lower()
    first_name = first_name.strip()
    surname = surname.strip()
    phone = phone.strip()
    secret_question = secret_question.strip()
    secret_answer = secret_answer.strip()

    if not email:
        return False, "Email is required."

    if not first_name:
        return False, "First name is required."

    if not surname:
        return False, "Surname is required."

    if not phone:
        return False, "Phone is required."

    if not password:
        return False, "Password is required."

    try:
        parsed_date_of_birth = datetime.strptime(
            date_of_birth,
            "%Y-%m-%d"
        ).date()
    except ValueError:
        return False, "date_of_birth must be in YYYY-MM-DD format."

    check_sql = """
        SELECT user_id
        FROM users
        WHERE email = %s
    """

    insert_sql = """
        INSERT INTO users (
            user_id,
            email,
            first_name,
            surname,
            phone,
            date_of_birth,
            password,
            secret_question,
            secret_answer
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(check_sql, (email,))
            existing_user = cur.fetchone()

            if existing_user is not None:
                return False, "Email is already registered."

            for _ in range(10):
                user_id = "RU" + "".join(
                    random.choices(
                        string.ascii_uppercase + string.digits,
                        k=6
                    )
                )

                try:
                    cur.execute(
                        insert_sql,
                        (
                            user_id,
                            email,
                            first_name,
                            surname,
                            phone,
                            parsed_date_of_birth,
                            password,
                            secret_question,
                            secret_answer,
                        ),
                    )

                    return True, user_id

                except psycopg2.errors.UniqueViolation:
                    conn.rollback()

            return False, "Could not generate a unique user ID."
#booking execution query
def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Create a national rail booking for a logged-in user.

    Args:
        user_id: User ID, e.g. "RU01".
        schedule_id: National rail schedule ID, e.g. "NR_SCH01".
        origin_station_id: Origin national rail station ID, e.g. "NR01".
        destination_station_id: Destination national rail station ID, e.g. "NR05".
        travel_date: Travel date in YYYY-MM-DD format.
        fare_class: Fare class, e.g. "standard" or "first".
        seat_id: Seat ID, or "any" to auto-select the first available seat.
        ticket_type: Ticket type, default is "single".

    Returns:
        (True, booking_dict) on success.
        (False, error_message) on failure.
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            selected_seat_id = seat_id

            if seat_id.lower() == "any":
                available_seats = query_available_seats(
                    schedule_id=schedule_id,
                    travel_date=travel_date,
                    fare_class=fare_class,
                )

                if not available_seats:
                    conn.rollback()
                    return False, "No available seats for this schedule, date, and fare class."

                selected_seat_id = available_seats[0]["seat_id"]

            booking_sql = """
                SELECT
                    nrs.schedule_id,
                    (
                    nrs.first_train_time
                    + os.travel_time_from_origin_min * INTERVAL '1 minute'
                    ) AS departure_time,
                    nrs.service_type,

                    os.stop_order AS origin_stop_order,
                    ds.stop_order AS destination_stop_order,
                    ds.stop_order - os.stop_order AS stops_travelled,

                    ns.coach,
                    ns.seat_id,

                    f.fare_class,
                    f.base_fare_usd,
                    f.per_stop_rate_usd,
                    (
                        f.base_fare_usd
                        + f.per_stop_rate_usd * (ds.stop_order - os.stop_order)
                    ) AS amount_usd

                FROM national_rail_schedules nrs

                JOIN national_rail_schedule_stops os
                    ON os.schedule_id = nrs.schedule_id
                   AND os.station_id = %s

                JOIN national_rail_schedule_stops ds
                    ON ds.schedule_id = nrs.schedule_id
                   AND ds.station_id = %s

                JOIN national_rail_schedule_fares f
                    ON f.schedule_id = nrs.schedule_id
                   AND f.fare_class = %s

                JOIN national_rail_seats ns
                    ON ns.schedule_id = nrs.schedule_id
                   AND ns.seat_id = %s

                JOIN national_rail_coaches c
                    ON c.schedule_id = ns.schedule_id
                   AND c.coach = ns.coach
                   AND c.fare_class = %s

                LEFT JOIN bookings b
                    ON b.schedule_id = ns.schedule_id
                   AND b.coach = ns.coach
                   AND b.seat_id = ns.seat_id
                   AND b.travel_date = %s
                   AND b.status <> 'cancelled'

                WHERE nrs.schedule_id = %s
                  AND os.stop_order < ds.stop_order
                  AND b.booking_id IS NULL

                ORDER BY
                    ns.coach,
                    ns.row_number,
                    ns.seat_column

                LIMIT 1
            """

            cur.execute(
                booking_sql,
                (
                    origin_station_id,
                    destination_station_id,
                    fare_class,
                    selected_seat_id,
                    fare_class,
                    travel_date,
                    schedule_id,
                ),
            )

            booking_info = cur.fetchone()

            if booking_info is None:
                conn.rollback()
                return False, "No valid available seat found for this journey."

            booking_id = _gen_booking_id()
            payment_id = _gen_payment_id()

            insert_booking_sql = """
                INSERT INTO bookings (
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    departure_time,
                    ticket_type,
                    fare_class,
                    coach,
                    seat_id,
                    stops_travelled,
                    amount_usd,
                    status,
                    booked_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    departure_time::text AS departure_time,
                    ticket_type,
                    fare_class,
                    coach,
                    seat_id,
                    stops_travelled,
                    amount_usd,
                    status,
                    booked_at
            """

            now = datetime.now(timezone.utc)

            cur.execute(
                insert_booking_sql,
                (
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    booking_info["departure_time"],
                    ticket_type,
                    fare_class,
                    booking_info["coach"],
                    booking_info["seat_id"],
                    booking_info["stops_travelled"],
                    booking_info["amount_usd"],
                    "confirmed",
                    now,
                ),
            )

            booking_row = dict(cur.fetchone())

            insert_payment_sql = """
                INSERT INTO payments (
                    payment_id,
                    transaction_ref,
                    amount_usd,
                    method,
                    status,
                    paid_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            cur.execute(
                insert_payment_sql,
                (
                    payment_id,
                    booking_id,
                    booking_info["amount_usd"],
                    "card",
                    "paid",
                    now,
                ),
            )

            conn.commit()
            return True, booking_row

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, "Seat is already booked or generated ID already exists."

    except psycopg2.Error as e:
        conn.rollback()
        return False, f"Database error: {e}"

    finally:
        conn.close()
#booking cancellation query
def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancel a national rail booking owned by the given user.

    Calculates the refund amount according to the booking's service type:
      - Normal service: RF001 windows (100% / 75% / 50% / 0%)
      - Express service: RF002 windows (100% / 50% / 0%)

    Args:
        booking_id: e.g. "BK001"
        user_id: must match the booking's user_id

    Returns:
        (True, result_dict) with refund_amount_usd and policy note.
        (False, error_msg) on failure.
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            booking_sql = """
                SELECT
                    b.booking_id,
                    b.user_id,
                    b.schedule_id,
                    b.origin_station_id,
                    origin_station.name AS origin_name,
                    b.destination_station_id,
                    destination_station.name AS destination_name,
                    b.travel_date,
                    b.departure_time,
                    b.ticket_type,
                    b.fare_class,
                    b.coach,
                    b.seat_id,
                    b.amount_usd,
                    b.status,
                    nrs.service_type
                FROM bookings b
                JOIN national_rail_schedules nrs
                    ON nrs.schedule_id = b.schedule_id
                JOIN national_rail_stations origin_station
                    ON origin_station.station_id = b.origin_station_id
                JOIN national_rail_stations destination_station
                    ON destination_station.station_id = b.destination_station_id
                WHERE b.booking_id = %s
                  AND b.user_id = %s
                FOR UPDATE
            """

            cur.execute(booking_sql, (booking_id, user_id))
            booking = cur.fetchone()

            if booking is None:
                conn.rollback()
                return False, "Booking not found or does not belong to this user."

            if booking["status"] == "cancelled":
                conn.rollback()
                return False, "Booking is already cancelled."

            departure_datetime = datetime.combine(
                booking["travel_date"],
                booking["departure_time"],
            ).replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)

            hours_before_departure = Decimal(
                str((departure_datetime - now).total_seconds() / 3600)
            )

            policy_sql = """
                SELECT
                    rp.policy_id,
                    rp.label AS policy_label,
                    rp.service_type,
                    w.window_id,
                    w.label AS window_label,
                    w.condition AS window_condition,
                    w.refund_percent,
                    w.admin_fee_usd
                FROM refund_policies rp
                JOIN refund_policy_cancellation_windows w
                    ON w.policy_id = rp.policy_id
                WHERE rp.network_type = 'national_rail'
                  AND (
                        rp.service_type = %s
                        OR rp.service_type IS NULL
                  )
                  AND (
                        w.hours_before_departure_min IS NULL
                        OR %s >= w.hours_before_departure_min
                  )
                  AND (
                        w.hours_before_departure_max IS NULL
                        OR %s < w.hours_before_departure_max
                  )
                ORDER BY
                    CASE
                        WHEN rp.service_type = %s THEN 0
                        ELSE 1
                    END,
                    w.refund_percent DESC
                LIMIT 1
            """

            cur.execute(
                policy_sql,
                (
                    booking["service_type"],
                    hours_before_departure,
                    hours_before_departure,
                    booking["service_type"],
                ),
            )

            policy = cur.fetchone()

            if policy is not None:
                refund_percent = Decimal(policy["refund_percent"])
                admin_fee_usd = Decimal(policy["admin_fee_usd"])
                policy_id = policy["policy_id"]
                policy_label = policy["policy_label"]
                window_label = policy["window_label"]
                policy_note = policy["window_condition"]

            else:
                service_type = booking["service_type"]
                policy_id = "fallback"
                policy_label = "Fallback cancellation policy"
                admin_fee_usd = Decimal("0.00")

                if service_type == "express":
                    if hours_before_departure >= Decimal("24"):
                        refund_percent = Decimal("100")
                        window_label = "24+ hours before departure"
                    elif hours_before_departure >= Decimal("4"):
                        refund_percent = Decimal("50")
                        window_label = "4–24 hours before departure"
                    else:
                        refund_percent = Decimal("0")
                        window_label = "Less than 4 hours before departure"

                else:
                    if hours_before_departure >= Decimal("24"):
                        refund_percent = Decimal("100")
                        window_label = "24+ hours before departure"
                    elif hours_before_departure >= Decimal("12"):
                        refund_percent = Decimal("75")
                        window_label = "12–24 hours before departure"
                    elif hours_before_departure >= Decimal("2"):
                        refund_percent = Decimal("50")
                        window_label = "2–12 hours before departure"
                    else:
                        refund_percent = Decimal("0")
                        window_label = "Less than 2 hours before departure"

                policy_note = "Refund calculated using fallback policy because no matching database policy window was found."

            original_amount = Decimal(booking["amount_usd"])

            refund_amount = (
                original_amount * refund_percent / Decimal("100")
                - admin_fee_usd
            )

            if refund_amount < Decimal("0.00"):
                refund_amount = Decimal("0.00")

            refund_amount = refund_amount.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            update_sql = """
                UPDATE bookings
                SET status = 'cancelled'
                WHERE booking_id = %s
                  AND user_id = %s
                RETURNING
                    booking_id,
                    user_id,
                    schedule_id,
                    origin_station_id,
                    destination_station_id,
                    travel_date,
                    departure_time::text AS departure_time,
                    ticket_type,
                    fare_class,
                    coach,
                    seat_id,
                    amount_usd,
                    status
            """

            cur.execute(update_sql, (booking_id, user_id))
            updated_booking = dict(cur.fetchone())

            conn.commit()

            return True, {
                "booking": updated_booking,
                "service_type": booking["service_type"],
                "hours_before_departure": round(float(hours_before_departure), 2),
                "original_amount_usd": original_amount,
                "refund_percent": refund_percent,
                "admin_fee_usd": admin_fee_usd,
                "refund_amount_usd": refund_amount,
                "policy_id": policy_id,
                "policy_label": policy_label,
                "window_label": window_label,
                "policy_note": policy_note,
            }

    except psycopg2.Error as e:
        conn.rollback()
        return False, f"Database error: {e}"

    finally:
        conn.close()
def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
