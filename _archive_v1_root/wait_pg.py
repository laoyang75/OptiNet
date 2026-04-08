import time
import subprocess
import json

def get_running_queries():
    sql = """
    SELECT count(*) 
    FROM pg_stat_activity 
    WHERE query ILIKE '%CREATE TABLE rebuild2.l0_%' AND state != 'idle' AND pid <> pg_backend_pid();
    """
    cmd = [
        "sshpass", "-p", "111111", "ssh", "root@192.168.200.217",
        f"PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2 -t -c \"{sql}\""
    ]
    try:
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return int(res.decode().strip())
    except:
        return 0

print("Waiting for L0 queries to complete...")
while True:
    count = get_running_queries()
    if count == 0:
        print("All L0 queries completed!")
        break
    time.sleep(30)
