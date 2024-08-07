# -*- mode: ruby -*-
# vi: set ft=ruby :

INTEL_BOX = "generic/ubuntu2204"
ARM_BOX = "perk/ubuntu-2204-arm64"


def get_box
  # Detect host architecture
  host_arch = `uname -m`

  if host_arch.include? 'x86_64'
    return INTEL_BOX
  elsif host_arch.include? 'arm'
    return ARM_BOX
  elsif host_arch.include? 'aarch64'
    return ARM_BOX
  else
    raise 'Unsupported architecture'
  end
end


Vagrant.configure("2") do |config|
  config.vm.box = get_box()
  config.vm.synced_folder ".", "/vagrant", type: "rsync"
  config.vm.provider "qemu" do |qemu|
    qemu.memory = 2048
    qemu.cpus = 2
  end
end
