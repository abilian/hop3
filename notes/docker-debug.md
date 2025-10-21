```bash
# Interactive bash shell in the container
docker exec -it hop3-debug-container bash
```


Once inside, useful commands:

```bash
# Check running processes
ps aux

# Check supervisor status
supervisorctl status

# View nginx logs (no hop3-server log file exists)
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log

# Check deployed apps
ls -la /home/hop3/apps/

# Switch to hop3 user
su - hop3

# Check nginx config
cat /etc/nginx/sites-enabled/hop3

# Run hop3 commands (use hop-server local, not hop3!)
# Option 1: From hop3 user
su - hop3
. venv/bin/activate
hop-server local apps
hop-server local app:status <app-name>

# Option 2: Directly as root
/home/hop3/venv/bin/hop-server local apps
```

Quick reference for inside the container:

```bash
# List apps
hop-server local apps

# Check app status
hop-server local app:status manual-app-1761027512

# View app directory
ls -la /home/hop3/apps/manual-app-1761027512/
```

To exit the shell: type exit or press Ctrl+D.
