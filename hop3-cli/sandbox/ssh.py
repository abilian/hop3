from paramiko.client import SSHClient


def main():
    client = SSHClient()
    client.load_system_host_keys()
    client.connect('c17.abilian.com')
    stdin, stdout, stderr = client.exec_command('ls -l')
    print(stdout.read())
    print(stderr.read())


main()
