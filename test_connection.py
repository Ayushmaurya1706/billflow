import psycopg2

# Supabase default port 5432 is commonly blocked in corporate or restricted network environments.
# Using port 6543 (transaction pooler) bypasses this block and connects successfully.
URL = "postgresql://postgres.gpesqpcmohvuxsbvtmrv:B018e3lHORZ5GtAu@aws-1-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require"

print("Testing database connection to Supabase...")
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
    print("\nTip: If you encounter timeout errors, ensure port 6543 is used in your DATABASE_URL environment variable and sslmode=require is set.")
