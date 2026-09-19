# CLI Reference

```
setup-ai start      # systemctl start firewing
setup-ai stop       # systemctl stop firewing
setup-ai restart    # systemctl restart firewing
setup-ai status     # systemctl status firewing
setup-ai logs       # journalctl -u firewing -f
setup-ai update     # pull + reinstall + restart (placeholder — wire to your deploy method)
setup-ai config     # print resolved configuration
setup-ai model      # print base model + license info
setup-ai doctor     # hardware/environment check (OS, CPU, RAM, GPU, CUDA, disk, Docker)
setup-ai chat        # interactive REPL against the local model
setup-ai --version
setup-ai --config <path>   # use a specific config file for any subcommand
```

`start`/`stop`/`restart`/`status`/`logs` shell out to `systemctl`/
`journalctl` and expect the systemd service installed by `install.sh`
to exist. Running them without that service installed will just
surface the underlying `systemctl` error.
