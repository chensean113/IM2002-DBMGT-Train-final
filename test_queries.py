import random
import string

import psycopg2.extras

from databases.relational.queries import (
    _connect,
    query_user_profile,
    login_user,
    get_user_secret_question,
    verify_secret_answer,
    update_password,
    register_user,
    query_metro_fare,
    query_national_rail_fare,
    query_available_seats,
    auto_select_adjacent_seats,
    query_metro_schedules,
    query_national_rail_availability,
    query_user_bookings,
    query_payment_info,
    execute_booking,
    execute_cancellation,
)


def section(title: str) -> None:
    print("\n" + "=" * 20)
    print(title)
    print("=" * 20)


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None


def main() -> None:
    section("1. Existing user sample")

    existing_user = fetch_one(
        """
        SELECT
            u.user_id,
            u.email,
            u.full_name,
            p.password,
            q.secret_answer
        FROM users u
        JOIN user_passwords p
            ON p.user_id = u.user_id
        JOIN user_security_questions q
            ON q.user_id = u.user_id
        LIMIT 1
        """
    )

    if existing_user is None:
        print("No existing users found. Check seed_postgres.py.")
    else:
        print(existing_user)

        section("2. query_user_profile")
        print(query_user_profile(existing_user["email"]))

        section("3. login_user")
        print(login_user(existing_user["email"], existing_user["password"]))

        section("4. get_user_secret_question")
        print(get_user_secret_question(existing_user["email"]))

        section("5. verify_secret_answer")
        print(verify_secret_answer(existing_user["email"], existing_user["secret_answer"]))

        section("6. query_user_bookings")
        print(query_user_bookings(existing_user["email"]))

    section("7. register_user + login_user + update_password")

    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    test_email = f"test_{suffix}@example.com"
    old_password = "oldpass123"
    new_password = "newpass456"

    success, result = register_user(
        email=test_email,
        first_name="Test",
        surname="User",
        year_of_birth=2000,
        password=old_password,
        secret_question="Favorite color?",
        secret_answer="Blue",
    )

    print("register_user:", success, result)

    if success:
        new_user_id = result

        print("login old password:")
        print(login_user(test_email, old_password))

        print("secret question:")
        print(get_user_secret_question(test_email))

        print("verify answer:")
        print(verify_secret_answer(test_email, "blue"))

        print("update password:")
        print(update_password(test_email, new_password))

        print("login new password:")
        print(login_user(test_email, new_password))
    else:
        new_user_id = None

    section("8. Metro fare")

    metro_schedule = fetch_one(
        """
        SELECT schedule_id
        FROM metro_schedules
        LIMIT 1
        """
    )

    if metro_schedule:
        print(query_metro_fare(metro_schedule["schedule_id"], 5))
    else:
        print("No metro schedule found.")

    section("9. Metro schedules")

    metro_route = fetch_one(
        """
        SELECT
            s1.station_id AS origin_id,
            s2.station_id AS destination_id
        FROM metro_schedule_stops s1
        JOIN metro_schedule_stops s2
            ON s2.schedule_id = s1.schedule_id
        WHERE s1.stop_order < s2.stop_order
        LIMIT 1
        """
    )

    if metro_route:
        print(
            query_metro_schedules(
                metro_route["origin_id"],
                metro_route["destination_id"],
            )
        )
    else:
        print("No metro route found.")

    section("10. National rail fare / availability / seats")

    nr_route = fetch_one(
        """
        SELECT
            nrs.schedule_id,
            f.fare_class,
            s1.station_id AS origin_id,
            s2.station_id AS destination_id,
            s2.stop_order - s1.stop_order AS stops_travelled
        FROM national_rail_schedules nrs
        JOIN national_rail_schedule_stops s1
            ON s1.schedule_id = nrs.schedule_id
        JOIN national_rail_schedule_stops s2
            ON s2.schedule_id = nrs.schedule_id
        JOIN national_rail_schedule_fares f
            ON f.schedule_id = nrs.schedule_id
        WHERE s1.stop_order < s2.stop_order
        LIMIT 1
        """
    )

    travel_date = "2026-12-01"

    if nr_route:
        print("NR route:")
        print(nr_route)

        print("query_national_rail_fare:")
        print(
            query_national_rail_fare(
                nr_route["schedule_id"],
                nr_route["fare_class"],
                nr_route["stops_travelled"],
            )
        )

        print("query_national_rail_availability:")
        print(
            query_national_rail_availability(
                nr_route["origin_id"],
                nr_route["destination_id"],
                travel_date,
            )
        )

        print("query_available_seats:")
        seats = query_available_seats(
            nr_route["schedule_id"],
            travel_date,
            nr_route["fare_class"],
        )
        print(seats[:5])

        print("auto_select_adjacent_seats:")
        print(auto_select_adjacent_seats(seats, 2))
    else:
        seats = []
        print("No national rail route found.")

    section("11. execute_booking + query_payment_info + execute_cancellation")

    if new_user_id and nr_route and seats:
        seat_id = seats[0]["seat_id"]

        booking_success, booking_result = execute_booking(
            user_id=new_user_id,
            schedule_id=nr_route["schedule_id"],
            origin_station_id=nr_route["origin_id"],
            destination_station_id=nr_route["destination_id"],
            travel_date=travel_date,
            fare_class=nr_route["fare_class"],
            seat_id=seat_id,
            ticket_type="single",
        )

        print("execute_booking:")
        print(booking_success, booking_result)

        if booking_success:
            booking_id = booking_result["booking_id"]

            print("query_payment_info:")
            print(query_payment_info(booking_id))

            print("execute_cancellation:")
            print(execute_cancellation(booking_id, new_user_id))
    else:
        print("Skipped booking test because user, route, or seats are missing.")


if __name__ == "__main__":
    main()