from config import BASE_DATE, UNIT_MAPPING_CSV
from machine_master import get_assignments_for_date, load_assignments


def main():
    assignments = load_assignments(UNIT_MAPPING_CSV)
    active = get_assignments_for_date(assignments, BASE_DATE)

    print("[OK] unit_mapping.csv の整合性チェックに成功しました")
    print(f"[DATE] {BASE_DATE.isoformat()}")
    print(f"[ACTIVE] {len(active)}台")

    current_store = None
    for a in active:
        if a.store_id != current_store:
            current_store = a.store_id
            print(f"\nstore_id={current_store}")
        print(
            f"  {a.machine_id}: unit={a.unit} / model={a.model}"
        )


if __name__ == "__main__":
    main()
