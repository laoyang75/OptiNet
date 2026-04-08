import paramiko

def execute_remote():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting to 192.168.200.217...")
    ssh.connect('192.168.200.217', username='root', password='111111')

    sftp = ssh.open_sftp()
    print("Uploading generate_l0_gps_part3.sql...")
    sftp.put('/Users/yangcongan/cursor/WangYou_Data/generate_l0_gps_part3.sql', '/tmp/generate_l0_gps_part3.sql')
    print("Uploading generate_l0_lac.sql...")
    sftp.put('/Users/yangcongan/cursor/WangYou_Data/generate_l0_lac.sql', '/tmp/generate_l0_lac.sql')
    sftp.close()

    print("Executing GPS part3 script via nohup...")
    stdin, stdout, stderr = ssh.exec_command('export PGPASSWORD=123456; nohup psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2 -f /tmp/generate_l0_gps_part3.sql > /tmp/gps_part3.log 2>&1 &')
    print(stdout.read().decode())
    
    print("Executing LAC script via nohup...")
    stdin, stdout, stderr = ssh.exec_command('export PGPASSWORD=123456; nohup psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2 -f /tmp/generate_l0_lac.sql > /tmp/lac.log 2>&1 &')
    print(stdout.read().decode())

    ssh.close()
    print("Jobs submitted to background on remote server.")

if __name__ == '__main__':
    execute_remote()
