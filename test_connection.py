import psycopg2

URL = "postgresql://postgres.gpesqpcmohvuxsbvtmrv:B018e3lHORZ5GtAu@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

print("Testing connection...")
try:
    conn = psycopg2.connect(URL, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT current_user, current_database(), version();")
    row = cur.fetchone()
    print(f"SUCCESS! user='{row[0]}' db='{row[1]}'")
    print(f"PG: {row[2][:60]}")
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {tables}")
    conn.close()
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
