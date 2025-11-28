## testing unde vagrant


```
# Install cli
HOP3_LOCAL_INSTALLER=/vagrant/installer/install-cli.py \
  bash /vagrant/installer/install-cli.sh --git --branch installer

# Install server
sudo HOP3_LOCAL_INSTALLER=/vagrant/installer/install-server.py \
  bash /vagrant/installer/install-server.sh --git --branch installer
```
