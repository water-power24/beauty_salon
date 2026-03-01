import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional


DB_PATH = Path(__file__).parent / "beauty_salon.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            duration_minutes INTEGER NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            service_id INTEGER NOT NULL,
            datetime TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services(id)
        );
        """
    )

    conn.commit()
    conn.close()


# ---------- Services ----------

def add_service(
    category: str,
    name: str,
    description: str,
    price: float,
    duration_minutes: int,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO services (category, name, description, price, duration_minutes)
        VALUES (?, ?, ?, ?, ?);
        """,
        (category, name, description, price, duration_minutes),
    )
    conn.commit()
    service_id = cur.lastrowid
    conn.close()
    return service_id


def delete_service(service_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM services WHERE id = ?;", (service_id,))
    conn.commit()
    conn.close()


def update_service_price(service_id: int, price: float) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE services SET price = ? WHERE id = ?;",
        (price, service_id),
    )
    conn.commit()
    conn.close()


def update_service_duration(service_id: int, duration_minutes: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE services SET duration_minutes = ? WHERE id = ?;",
        (duration_minutes, service_id),
    )
    conn.commit()
    conn.close()


def get_categories() -> List[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM services ORDER BY category;")
    rows = cur.fetchall()
    conn.close()
    return [row["category"] for row in rows]


def get_services_by_category(category: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, description, price, duration_minutes
        FROM services
        WHERE category = ?
        ORDER BY name;
        """,
        (category,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_services() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, category, name, description, price, duration_minutes
        FROM services
        ORDER BY category, name;
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_service(service_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, category, name, description, price, duration_minutes
        FROM services
        WHERE id = ?;
        """,
        (service_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------- Bookings ----------

def add_booking(
    user_id: int,
    username: Optional[str],
    full_name: str,
    phone: str,
    service_id: int,
    dt: str,
    created_at: str,
    status: str = "new",
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO bookings (
            user_id, username, full_name, phone,
            service_id, datetime, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (user_id, username, full_name, phone, service_id, dt, status, created_at),
    )
    conn.commit()
    booking_id = cur.lastrowid
    conn.close()
    return booking_id


def get_last_bookings(limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            b.id,
            b.user_id,
            b.username,
            b.full_name,
            b.phone,
            b.datetime,
            b.status,
            b.created_at,
            s.name AS service_name,
            s.category AS service_category,
            s.price AS service_price
        FROM bookings b
        JOIN services s ON s.id = b.service_id
        ORDER BY b.id DESC
        LIMIT ?;
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_bookings_for_service_on_date(
    service_id: int,
    date_str: str,
) -> List[Dict[str, Any]]:
    """
    Вернёт все записи на указанную дату для услуги.

    date_str ожидается в формате 'YYYY-MM-DD'.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, datetime, status
        FROM bookings
        WHERE service_id = ?
          AND datetime LIKE ? || '%'
        ORDER BY datetime;
        """,
        (service_id, date_str),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

