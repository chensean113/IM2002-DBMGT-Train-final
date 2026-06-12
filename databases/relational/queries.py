from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD
import random
import string
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import bcrypt
from typing import Optional
import psycopg2
import psycopg2.extras


def _connect():
    """
    Return a new psycopg2 connection with autocommit enabled.


    Args:
        None.


    Returns:
        A psycopg2 database connection.
    """
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn




def _gen_booking_id() -> str:
    """
    Generate a random booking ID.


    Args:
        None.


    Returns:
        Booking ID string in the format BK-XXXXXX.
    """
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"




def _gen_payment_id() -> str:
    """
    Generate a random payment ID.


    Args:
        None.


    Returns:
        Payment ID string in the format PM-XXXXXX.
    """
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"




def _vector_literal(embedding: list[float]) -> str:
    """
    Convert an embedding list into pgvector literal syntax.


    Args:
        embedding: List of numeric embedding values.


    Returns:
        pgvector-compatible string, e.g. "[0.1,0.2]".
    """
    return "[" + ",".join(str(x) for x in embedding) + "]"
#user profile
def query_user_profile(user_email: str) -> Optional[dict]:
    """
    Return a user's profile by email.


    Args:
        user_email: User email address.


    Returns:
        User profile dictionary or None if not found.
    """
    sql = """
        SELECT
            u.user_id,
            u.email,
            u.full_name,
            u.phone,
            u.date_of_birth,
            u.is_active,
            u.registered_at,
            q.secret_question
        FROM users u
        LEFT JOIN user_security_questions q
            ON q.user_id = u.user_id
        WHERE u.email = %s
    """


    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (user_email,))
            row = cur.fetchone()


            if row is None:
                return None


            result = dict(row)


            name_parts = result["full_name"].split(" ", 1)
            result["first_name"] = name_parts[0]
            result["surname"] = name_parts[1] if len(name_parts) > 1 else ""


            return result
#login user
def login_user(email: str, password: str) -> Optional[dict]:
    """
    Verify credentials.


    Args:
        email: User email address.
        password: User password.


    Returns:
        User dictionary on success, None on failure.
    """
    sql = """
        SELECT
            u.user_id,
            u.email,
            u.full_name,
            u.phone,
            u.date_of_birth,
            u.is_active,
            p.password
        FROM users u
        JOIN user_passwords p
            ON p.user_id = u.user_id
        WHERE u.email = %s
          AND u.is_active = TRUE
    """


    with _connect() as conn:
        with conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()


            if row is None:
                return None


            stored_password = row["password"]
            if isinstance(stored_password, str):
                stored_password = stored_password.encode("utf-8")


            if not bcrypt.checkpw(password.encode("utf-8"), stored_password):
                return None


            result = dict(row)
            result.pop("password", None)


            name_parts = result["full_name"].split(" ", 1)
            result["first_name"] = name_parts[0]
            result["surname"] = name_parts[1] if len(name_parts) > 1 else ""


            return result
#user secret question
def get_user_secret_question(email: str) -> Optional[str]:
    """
    Return the secret question for a registered email, or None if not found.


    Args:
        email: User email address.


    Returns:
        Secret question string or None.
    """
    sql = """
        SELECT q.secret_question
        FROM users u
        JOIN user_security_questions q
            ON q.user_id = u.user_id
        WHERE u.email = %s
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
    Return True if the provided answer matches the stored secret answer.


    Args:
        email: User email address.
        answer: Answer provided by user.


    Returns:
        True if answer matches, otherwise False.
    """
    sql = """
        SELECT q.secret_answer
        FROM users u
        JOIN user_security_questions q
            ON q.user_id = u.user_id
        WHERE u.email = %s
    """


    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()


            if row is None:
                return False


            stored_answer = row[0]


            return stored_answer.strip().lower() == answer.strip().lower()
#update user password
def update_password(email: str, new_password: str) -> bool:
    """
    Update the password for a user.


    Args:
        email: User email address.
        new_password: New password.


    Returns:
        True if updated successfully, False otherwise.
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed_password = bcrypt.hashpw(
        new_password.encode("utf-8"),
        salt,
    ).decode("utf-8")


    sql = """
        UPDATE user_passwords p
                SET password = %s,
                        salt = %s
        FROM users u
        WHERE p.user_id = u.user_id
          AND u.email = %s
    """


    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False


    try:
        with conn.cursor() as cur:
            cur.execute(sql, (hashed_password, salt.decode("utf-8"), email))
            updated = cur.rowcount > 0
            if updated:
                conn.commit()
            else:
                conn.rollback()
            return updated
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        conn.close()
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
                Decimal(str(result["base_fare_usd"]))
                + Decimal(str(result["per_stop_rate_usd"])) * stops_travelled
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
                Decimal(str(result["base_fare_usd"]))
                + Decimal(str(result["per_stop_rate_usd"])) * stops_travelled
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
    List available seats for a given schedule, date, and fare class.


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
           AND b.travel_date = %s::date  
           AND b.status <> 'cancelled'
        WHERE s.schedule_id = %s
          AND LOWER(c.fare_class) = LOWER(%s) 
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
def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    """
    Select `count` seats that are as close together as possible.


    Args:
        available_seats: output of query_available_seats()
        count: number of seats needed


    Returns:
        List of selected seat IDs.
    """
    if not available_seats or count <= 0:
        return []


    if count >= len(available_seats):
        return [seat["seat_id"] for seat in available_seats[:count]]


    from collections import defaultdict


    seats_by_row: dict[tuple[str, int], list[dict]] = defaultdict(list)


    for seat in available_seats:
        seats_by_row[(seat["coach"], seat["row"])].append(seat)


    for row_key in sorted(seats_by_row.keys(), key=lambda x: (x[0], x[1])):
        row_seats = sorted(
            seats_by_row[row_key],
            key=lambda seat: seat["column"]
        )


        if len(row_seats) >= count:
            return [seat["seat_id"] for seat in row_seats[:count]]


    sorted_seats = sorted(
        available_seats,
        key=lambda seat: (
            seat["coach"],
            seat["row"],
            seat["column"]
        )
    )


    return [seat["seat_id"] for seat in sorted_seats[:count]]
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
    Return national rail schedules that serve both stations in the correct order.


    When travel_date is provided, booked_seats and available_seats are calculated
    for that date. When travel_date is None, booked_seats is returned as 0 and
    available_seats equals total_seats because no specific trip date was given.


    Args:
        origin_id: Origin national rail station ID, e.g. "NR01".
        destination_id: Destination national rail station ID, e.g. "NR05".
        travel_date: Optional travel date in YYYY-MM-DD format.


    Returns:
        List of matching national rail schedules with route, timing, and seat counts.
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


            COUNT(seat.seat_id) AS total_seats,
            COUNT(b.booking_id) AS booked_seats,
            COUNT(seat.seat_id) - COUNT(b.booking_id) AS available_seats


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
           AND b.coach = seat.coach
           AND b.seat_id = seat.seat_id
           AND b.status <> 'cancelled'
           AND %s::date IS NOT NULL
           AND b.travel_date = %s::date


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
        HAVING COUNT(seat.seat_id) > 0
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
                (origin_id, destination_id, travel_date, travel_date),
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
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Register a new user.


    Args:
        email: User email address.
        first_name: User first name.
        surname: User surname.
        year_of_birth: User birth year.
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
    full_name = f"{first_name} {surname}".strip()
    password = password.strip()
    secret_question = secret_question.strip()
    secret_answer = secret_answer.strip()


    if not email:
        return False, "Email is required."


    if not full_name:
        return False, "Full name is required."


    if not password:
        return False, "Password is required."


    try:
        parsed_date_of_birth = datetime.strptime(
            f"{year_of_birth}-01-01",
            "%Y-%m-%d"
        ).date()
    except ValueError:
        return False, "year_of_birth must be a valid year."


    salt = bcrypt.gensalt(rounds=12)
    hashed_password = bcrypt.hashpw(
        password.encode("utf-8"),
        salt,
    ).decode("utf-8")


    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False


    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id
                FROM users
                WHERE email = %s
                """,
                (email,),
            )


            if cur.fetchone() is not None:
                conn.rollback()
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
                        """
                        INSERT INTO users (
                            user_id,
                            email,
                            full_name,
                            phone,
                            date_of_birth
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            user_id,
                            email,
                            full_name,
                            "N/A",
                            parsed_date_of_birth,
                        ),
                    )


                    cur.execute(
                        """
                        INSERT INTO user_passwords (
                            user_id,
                            password,
                            salt
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            user_id,
                            hashed_password,
                            salt.decode("utf-8"),
                        ),
                    )


                    cur.execute(
                        """
                        INSERT INTO user_security_questions (
                            user_id,
                            secret_question,
                            secret_answer
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            user_id,
                            secret_question,
                            secret_answer,
                        ),
                    )


                    conn.commit()
                    return True, user_id


                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    continue


            conn.rollback()
            return False, "Could not generate a unique user ID."


    except psycopg2.Error as e:
        conn.rollback()
        return False, f"Database error: {e}"


    finally:
        conn.close()
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
    requested_seat_id = seat_id.strip()
    requested_seat_key = requested_seat_id.lower()


    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False


    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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


                JOIN national_rail_coaches c
                    ON c.schedule_id = ns.schedule_id
                   AND c.coach = ns.coach
                   AND c.fare_class = %s


                LEFT JOIN bookings b
                    ON b.schedule_id = ns.schedule_id
                   AND b.coach = ns.coach
                   AND b.seat_id = ns.seat_id
                   AND b.travel_date = %s::date
                   AND b.status <> 'cancelled'


                WHERE nrs.schedule_id = %s
                  AND os.stop_order < ds.stop_order
                  AND b.booking_id IS NULL
                  AND (%s = 'any' OR ns.seat_id = %s)


                ORDER BY
                    ns.coach,
                    ns.row_number,
                    ns.seat_column


                LIMIT 1
                FOR UPDATE OF ns SKIP LOCKED 
            """


            cur.execute(
                booking_sql,
                (
                    origin_station_id,
                    destination_station_id,
                    fare_class,
                    fare_class,
                    travel_date,
                    schedule_id,
                    requested_seat_key,
                    requested_seat_id,
                ),
            )


            booking_info = cur.fetchone()


            if booking_info is None:
                conn.rollback()
                return False, "No valid available seat found for this journey."


            booking_id = _gen_booking_id()
            payment_id = _gen_payment_id()
            now = datetime.now(timezone.utc)


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


    Args:
        embedding: Query embedding vector.
        top_k: Maximum number of policy documents to return.


    Returns:
        List of matching policy document dictionaries with similarity scores.
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
    vec_str = _vector_literal(embedding)


    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k),
            )
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


    Args:
        title: Policy document title.
        category: Policy document category.
        content: Full policy document text.
        embedding: Embedding vector for semantic search.
        source_file: Optional source filename.


    Returns:
        ID of the inserted policy document.
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = _vector_literal(embedding)


    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
