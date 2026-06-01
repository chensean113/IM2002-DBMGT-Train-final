from databases.relational.queries import (
    query_user_profile,
    query_metro_fare,
    query_national_rail_fare,
    query_metro_schedules,
    query_national_rail_availability,
    query_available_seats,
)

print("=== USER PROFILE ===")
print(query_user_profile("alice@example.com"))

print("=== METRO FARE ===")
print(query_metro_fare("MS_SCH01", 5))

print("=== NATIONAL RAIL FARE ===")
print(query_national_rail_fare("NR_SCH01", "standard", 4))

print("=== METRO SCHEDULES ===")
print(query_metro_schedules("MS01", "MS09"))

print("=== NATIONAL RAIL AVAILABILITY ===")
print(query_national_rail_availability("NR01", "NR05", "2026-06-01"))

print("=== AVAILABLE SEATS ===")
print(query_available_seats("NR_SCH01", "2026-06-01", "standard"))