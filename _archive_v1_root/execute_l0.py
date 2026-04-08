import paramiko

def execute_remote():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting to 192.168.200.217...")
    ssh.connect('192.168.200.217', username='root', password='111111')

    sftp = ssh.open_sftp()
    print("Uploading generate_l0_gps.sql...")
    sftp.put('/Users/yangcongan/cursor/WangYou_Data/generate_l0_gps.sql', '/tmp/generate_l0_gps.sql')
    print("Uploading generate_l0_lac.sql...")
    sftp.put('/Users/yangcongan/cursor/WangYou_Data/generate_l0_lac.sql', '/tmp/generate_l0_lac.sql')
    sftp.close()

    print("Files uploaded. Starting execution of GPS table (this may take 10-20 minutes)...")
    stdin, stdout, stderr = ssh.exec_command('PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2 -f /tmp/generate_l0_gps.sql')
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print("GPS execution failed:")
        print(stderr.read().decode())
        return
    print("GPS table completed.")
    print(stdout.read().decode())

    print("Starting execution of LAC table (this may take 10-20 minutes)...")
    stdin, stdout, stderr = ssh.exec_command('PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2 -f /tmp/generate_l0_lac.sql')
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print("LAC execution failed:")
        print(stderr.read().decode())
        return
    print("LAC table completed.")
    print(stdout.read().decode())
    
    ssh.close()
    print("All tasks completed.")

if __name__ == '__main__':
    execute_remote()
