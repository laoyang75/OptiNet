
import subprocess
import threading
import time
import datetime
import json
import re
import os
import signal

# --- Config ---
DB_CONN = "postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable"
RUN_ID = f"20251222_{int(time.time())}"
SQL_FILE_PATH = "../sql/30_step30_master_bs_library.sql"
OUTPUT_DIR = "."

# Performance parameters from step30fenxi.md
PARAMS = {
    "run_id": RUN_ID,
    "application_name_prefix": "codex_step30_agent",
    "smoke_report_date": "2025-12-01",
    "smoke_operator_id_raw": "46000",
    "work_mem": "512MB",
    "max_parallel_workers_per_gather": "16"
}

# --- Helpers ---
def run_psql(sql, json_output=False):
    """Run SQL via psql using subprocess."""
    cmd = ["psql", DB_CONN, "-X", "-v", "ON_ERROR_STOP=1"]
    if json_output:
        cmd.extend(["--no-align", "--tuples-only", "--pset=footer=off"])
    
    print(f"Executing SQL (len={len(sql)})...")
    # Pass SQL via stdin
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate(input=sql)
    
    if p.returncode != 0:
        print(f"SQL FAILURE. Return Code: {p.returncode}")
        print(f"STDOUT: {out}")
        print(f"STDERR: {err}")
        raise Exception(f"PSQL Error: {err}")
    
    # If successful, still print stderr as warnings might be there
    if err and "NOTICE" not in err: 
       # Filter out common notices if needed, but for now just print execution logs
       pass
       
    return out.strip()

def run_psql_file(filepath):
    """Run a SQL file."""
    with open(filepath, 'r') as f:
        sql = f.read()
    return run_psql(sql)

def get_dbstat():
    sql = """
    SELECT json_build_object(
        'ts', now(),
        'temp_files', temp_files,
        'temp_bytes', temp_bytes,
        'blks_read', blks_read,
        'blk_read_time', blk_read_time
    ) FROM pg_stat_database WHERE datname = current_database();
    """
    res = run_psql(sql, json_output=True)
    return json.loads(res)

# --- Sampler ---
class Sampler(threading.Thread):
    def __init__(self, run_id):
        super().__init__()
        self.run_id = run_id
        self.stop_event = threading.Event()
        self.samples_activity = []
        self.samples_dbstat = []
        
    def run(self):
        print(f"Sampler started for run {self.run_id}")
        last_dbstat = time.time()
        
        while not self.stop_event.is_set():
            # 1. Activity Sample (Every 2s)
            try:
                act_sql = f"""
                INSERT INTO public.codex_perf_samples_activity
                SELECT '{self.run_id}', now(), pid, leader_pid, backend_type, state, wait_event_type, wait_event, now()-query_start, left(query, 120)
                FROM pg_stat_activity
                WHERE application_name LIKE '%{self.run_id}%'
                RETURNING pid;
                """
                run_psql(act_sql)
            except Exception as e:
                pass # Ignore sampling errors

            # 2. DbStat Sample (Every 60s)
            if time.time() - last_dbstat > 30:
                try:
                    stat_sql = f"""
                    INSERT INTO public.codex_perf_samples_dbstat
                    SELECT '{self.run_id}', now(), temp_files, temp_bytes, blks_read, blks_hit, blk_read_time, blk_write_time
                    FROM pg_stat_database WHERE datname=current_database();
                    """
                    run_psql(stat_sql)
                    last_dbstat = time.time()
                except:
                    pass
            
            time.sleep(2)
            
    def stop(self):
        self.stop_event.set()
        self.join()

# --- Main Logic ---

def prepare_sql_content(base_sql, is_smoke=True, explain_mode=None):
    """
    Reads the base SQL, strips existing SET commands, adds our profile config.
    explain_mode: 'smoke' (Analyze), 'shape' (No Analyze), or None (Run).
    """
    # 1. Strip top-level SETs (Simple heuristic: lines starting with SET)
    lines = base_sql.splitlines()
    cleaned_lines = [l for l in lines if not l.strip().upper().startswith("SET ")]
    core_sql = "\n".join(cleaned_lines)
    
    # 2. Build Prefix
    smoke_val = 'true' if is_smoke else 'false'
    
    prefix = [
        f"SET application_name = '{PARAMS['application_name_prefix']}|run={PARAMS['run_id']}|smoke={smoke_val}';",
        f"SET statement_timeout = 0;",
        f"SET jit = off;",
        f"SET work_mem = '{PARAMS['work_mem']}';",
        f"SET max_parallel_workers_per_gather = {PARAMS['max_parallel_workers_per_gather']};",
        "SET hash_mem_multiplier = 2.0;",
        "SELECT set_config('codex.is_smoke', '{}', false);".format(smoke_val),
        "SELECT set_config('codex.smoke_report_date', '{}', false);".format(PARAMS['smoke_report_date']),
        "SELECT set_config('codex.smoke_operator_id_raw', '{}', false);".format(PARAMS['smoke_operator_id_raw'])
    ]
    
    full_sql = "\n".join(prefix) + "\n" + core_sql
    
    # 3. Wrap with EXPLAIN if needed
    if explain_mode == 'smoke':
        # Find the CREATE TABLE AS part
        # Regex to find "CREATE TABLE ... AS"
        # We assume the main statement is the CREATE TABLE. 
        # Ideally we wrap the whole thing or just the SELECT.
        # PG 15 supports EXPLAIN CREATE TABLE AS.
        # We need to find where CREATE starts.
        # But previous cleanup might have left comments.
        match = re.search(r'(CREATE\s+TABLE\s+["\w\.]+\s+AS)', full_sql, re.IGNORECASE)
        if match:
            full_sql = full_sql.replace(match.group(1), "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) " + match.group(1))
        else:
            print("WARNING: Could not find CREATE TABLE AS to wrap EXPLAIN")
            
    elif explain_mode == 'shape':
        match = re.search(r'(CREATE\s+TABLE\s+["\w\.]+\s+AS)', full_sql, re.IGNORECASE)
        if match:
            # For shape, we ideally don't run it (Analyze off), but Explain CTA will create the table structure? 
            # Actually EXPLAIN without ANALYZE on CTAS will NOT create the table.
            full_sql = full_sql.replace(match.group(1), "EXPLAIN (SETTINGS, FORMAT JSON) " + match.group(1))
            
    return full_sql

def main():
    print(f"--- Starting Profile Run {RUN_ID} ---")
    
    # 0. Load Base SQL
    with open(SQL_FILE_PATH, 'r') as f:
        base_sql = f.read()

    # 1. Setup Tables
    print("Setting up perf tables...")
    run_psql_file("setup_perf_tables.sql")
    
    # 2. Register Run
    meta_sql = f"""
    INSERT INTO public.codex_perf_runs(run_id, application_name, is_smoke, smoke_report_date, smoke_operator_id_raw)
    VALUES ('{RUN_ID}', '{PARAMS['application_name_prefix']}', true, '{PARAMS['smoke_report_date']}', '{PARAMS['smoke_operator_id_raw']}');
    """
    run_psql(meta_sql)
    
    # 3. Start Sampler
    sampler = Sampler(RUN_ID)
    sampler.start()
    
    try:
        # 4. EXPLAIN SMOKE (Targeting execution plan analysis)
        print("Running EXPLAIN (ANALYZE)... this might take a few minutes (smoke data)...")
        explain_sql = prepare_sql_content(base_sql, is_smoke=True, explain_mode='smoke')
        
        # We need to capture the JSON output. 
        # run_psql returns the output.
        try:
            plan_json = run_psql(explain_sql)
            # PG explain output might contain header/footer text if not careful, or just the JSON.
            # Using -tA in run_psql helps.
            # We save it.
            with open(f"explain_smoke_{RUN_ID}.json", "w") as f:
                f.write(plan_json)
            print("Captured explain_smoke.json")
        except Exception as e:
            print(f"Explain Smoke Failed: {e}")

        # 5. REAL RUN (Smoke)
        print("Running ACTUAL SMOKE EXECUTION...")
        start_ts = time.time()
        
        real_sql = prepare_sql_content(base_sql, is_smoke=True, explain_mode=None)
        run_psql(real_sql)
        
        duration = time.time() - start_ts
        print(f"Smoke Run Finished in {duration:.2f} seconds.")
        
        # 6. Post-Run Stats
        # Get row count/size
        size_sql = """
        SELECT json_build_object(
            'rows', (SELECT count(*) FROM public."Y_codex_Layer3_Step30_Master_BS_Library"),
            'bytes', pg_total_relation_size('public."Y_codex_Layer3_Step30_Master_BS_Library"')
        );
        """
        stats = run_psql(size_sql, json_output=True)
        print(f"Output Stats: {stats}")
        
    finally:
        sampler.stop()
        print("Sampler stopped.")

    # 7. Generate Report Trigger
    # (Simplified: we just point user to the explain json and logs)
    print("Generating bottleneck analysis...")
    
    # Basic Analysis from logs
    # Check for spills in Explain
    spill_detected = False
    try:
        with open(f"explain_smoke_{RUN_ID}.json") as f:
            content = f.read()
            if "Disk: true" in content or "external merge" in content:
                spill_detected = True
    except:
        pass
        
    print(f"Analysis Result: Spill Detected = {spill_detected}")
    
    report_md = f"""
# Step30 Performance Bottleneck Report (Run {RUN_ID})

## 1. Summary
- **Duration**: {duration:.2f}s
- **Spill Detected**: {spill_detected}
- **Run ID**: {RUN_ID}

## 2. Recommendations
{'- High Priority: Temp Spill detected. Increase work_mem or optimize sorts.' if spill_detected else '- No excessive spilling detected in smoke text.'}

## 3. Artifacts
- Plan: `explain_smoke_{RUN_ID}.json`
- Logs: Query table `public.codex_perf_samples_activity` using `run_id='{RUN_ID}'`.
    """
    
    with open("bottleneck_report.md", "w") as f:
        f.write(report_md)

if __name__ == "__main__":
    main()
