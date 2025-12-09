# FAQ

**Q: Why "Hop3"?**

**A:** "Hop3" means "hop cubed" or "hop to the power of 3", or "hop, hop, hop!", which in French means "hurry up!". This name reflects the agility, speed, and efficiency we aim for with this platform.

The number 3 is also a nod to the fact that it's the third iteration of a similar system we've been developing and using for years (Abilian Cloud Controller -> Nua -> Hop3).

**Q: What makes Hop3 different from other PaaS offerings?**

**A:** Hop3 distinguishes itself from other Platform as a Service (PaaS) offerings through its unique combination of simplicity, modularity, and commitment to open-source principles. Unlike many PaaS solutions that are either proprietary or that lean heavily on complex, resource-intensive containerization and orchestration tools like Docker and Kubernetes, Hop3 is designed to be lightweight and accessible, ensuring efficient performance even on low-end devices or in resource-constrained environments.

At its core, Hop3 is built to be highly extensible and customizable through a plugin-oriented architecture. This approach allows users to tailor the platform to their specific needs, extending its functionality without bloating the core system. This level of modularity is rare in the PaaS space, where platforms often trade off customizability for simplicity.

Hop3's open-source nature makes it easy to taylor or enhance the platform, share knowledge, and develop new features. This stands in contrast to many commercial PaaS offerings, where users are subject to the limitations and costs imposed by proprietary technologies and cannot directly influence the platform's development trajectory.

Hop3 prioritizes direct integration with the host system, offering improved performance and resource utilization over solutions that abstract away the underlying infrastructure. This direct approach also enhances security and reliability, as users maintain closer control over their deployment environments.

Finally, Hop3's philosophy eschews the complexity and overhead associated with larger platforms like Kubernetes, aiming instead to provide a straightforward and user-friendly deployment experience. This makes Hop3 particularly appealing to small to medium-sized projects, early-stage startups, and developers looking for an agile and cost-effective way to deploy and manage their applications, without sacrificing the power and flexibility typically associated with larger PaaS solutions.

**Q: Why Python? / why not Go/Rust/Erlang/...?**

**A:** Python was chosen for Hop3 for its simplicity, readability, and vast ecosystem, which are essential for a platform designed to be accessible and easily adopted by a broad range of developers.

While Go, Rust, Erlang, and other languages offer their own set of advantages, including performance and concurrency support, Python strikes an optimal balance between performance, ease of development, and community support. It also happens to be the language we are most comfortable with and have the most experience in.

**Q: Can Hop3 support applications built with various programming languages?**

**A:** Yes, Hop3 is designed to be language-agnostic, supporting a wide range of programming languages and frameworks. This flexibility allows developers to deploy applications written in languages like Python, JavaScript (Node.js), Ruby, Java, and more. The platform's underlying infrastructure and tooling are built to accommodate the diverse needs of modern web applications, ensuring that developers can use their preferred languages and technologies without compatibility concerns.

**Q: Why not just use Dokku?**

**A:** While Dokku was the original "self-hosted and lightweight Heroku-clone", Hop3 seeks to address certain limitations inherent in Dokku's architecture. Specifically, Dokku can be somewhat heavy for small-scale deployments or low-end hardware, and its customization options are limited by its reliance on Docker. Hop3 is engineered to be leaner, offering improved performance and security, and its modular, plugin-oriented design affords a level of flexibility and extensibility that Dokku lacks.

**Q: Why not just use Piku or Sailor?**

**A:** Both Piku and Sailor offer compelling solutions; however, Hop3 differentiates itself by focusing on providing a broader set of functionalities and a more polished user experience. We aim to support an expansive array of deployment contexts with enhanced ease of use. Although we share roots with Piku and Sailor, including some shared code, Hop3's architecture is conceived to be more openly extensible. This encourages not just the use but also the contribution to its ecosystem, with a particular emphasis on plugins that can broaden its applicability.

**Q: Why not use Docker or a similar container-based technology?**

**A:** Docker's complexity and the resource demand it places on systems, particularly for smaller projects or devices with limited capabilities, is a significant drawback. Hop3 aspires to offer a more streamlined, efficient alternative that sidesteps the bulk and intricacy of Docker, focusing instead on straightforward deployment processes. Our system is designed for deeper integration with the host and/or external services, optimizing both performance and resource use.

**Q: Why not use Kubernetes?**

**A:** Kubernetes, despite its scalability and robustness, often introduces unnecessary complexity and overhead for simpler applications or smaller-scale deployments. Hop3 is tailored for those seeking a more accessible, less cumbersome solution. Our platform avoids the steep learning curve and extensive setup associated with Kubernetes, offering a streamlined path to deploying applications efficiently.

**Q: Why not use Heroku?**

**A:** Heroku's ease of use and developer-friendly approach are commendable, but it comes at a cost—both literally and in terms of flexibility and control. Hop3 aims to deliver a more cost-effective, adaptable alternative that does not compromise on the breadth of deployment scenarios it supports. By fostering an open, plugin-enhanced ecosystem, Hop3 offers a level of customization and community engagement that Heroku cannot match, all while steering clear of proprietary confines.

**Q: Why not use platforms like Render, Vercel, Netlify, etc.?**

**A:** Platforms such as Render, Vercel, Netlify, etc. provide valuable services but often at the expense of flexibility, control, and cost. Hop3 is envisioned as a more versatile and economical alternative, empowering users with broader deployment capabilities and deeper customization options. Unlike these platforms, Hop3 champions open-source development, ensuring users aren't locked into proprietary ecosystems. This openness encourages innovation, collaboration, and a level of control over deployment environments that proprietary platforms can't match, making Hop3 an attractive option for those seeking greater autonomy in their development workflows.

**Q: How does Hop3 contribute to environmental sustainability?**

**A:** Hop3 contributes to environmental sustainability by optimizing resource usage and encouraging the adoption of green computing practices. Through efficient coding, resource allocation, and the utilization of energy-efficient technologies, Hop3 minimizes the carbon footprint associated with hosting and running web applications. Additionally, by providing developers with tools and guidelines for sustainable app development, Hop3 promotes practices that reduce electronic waste and encourage the use of renewable energy sources in cloud computing environments.

**Q: Why did Hop3 choose uWSGI for application deployment?**

**A:** The choice of [uWSGI](https://uwsgi-docs.readthedocs.io/) in [emperor mode](https://uwsgi-docs.readthedocs.io/en/latest/Emperor.html) for Hop3 was driven by its robust feature set that aligns with our core objectives of simplicity, performance, and security.

1. uWSGI offers seamless integration with Python WSGI applications and `virtualenvs`, making it an ideal tool for Python-based projects which constitute a significant portion of web applications today. This integration simplifies the deployment process, allowing developers to focus on their application logic rather than the intricacies of server configuration.

1. uWSGI provides a suite of process management features, including monitoring, restarting, and basic resource limiting, which are essential for maintaining the reliability and efficiency of applications. These capabilities ensure that apps remain responsive and stable under varying loads without requiring manual intervention, thereby enhancing the overall user experience.

While uWSGI has served Hop3 well, future versions of Hop3 will propose alternatives to uWSGI (as plugins), reflecting our commitment to flexibility and the desire to accommodate a broader range of use cases and technologies. [Potential alternatives are listed here](https://github.com/abilian/books/blob/main/uwsgi/chap-9-2.md).

More notes about uWSGI: <https://github.com/abilian/books/blob/main/uwsgi/README.md>

## Backup and Restore

**Q: How do I backup my applications?**

**A:** Hop3 provides a comprehensive backup system accessible via the CLI. To create a backup of an application, simply run:

```bash
hop3 backup:create <app-name>
```

This creates a complete backup including your source code, application data, environment variables, and any attached services (like PostgreSQL databases). Each backup is assigned a unique ID that you can use to restore later. For detailed information, see the [Backup and Restore Guide](backup-restore.md).

**Q: What is included in a Hop3 backup?**

**A:** A Hop3 backup includes everything needed to fully restore your application:

- **Source Code**: Complete git repository with all commits and history
- **Data Directory**: All application data files and user-uploaded content
- **Environment Variables**: All configuration settings (including secrets like API keys)
- **Attached Services**: Database dumps (PostgreSQL, etc.) and service configurations
- **Application Metadata**: Hostname, port settings, and deployment configuration

Each backup is verified with SHA256 checksums to ensure data integrity.

**Q: How do I restore from a backup?**

**A:** Restoring an application is straightforward:

```bash
hop3 backup:restore <backup-id>
hop3 app:restart <app-name>
```

Replace `<backup-id>` with the ID from your backup (e.g., `20251108_143022_a8f3d9`). You can find backup IDs by running `hop3 backup:list`. The restore process verifies checksums to ensure data integrity before restoring.

**Q: Can I backup to remote storage (S3, etc.)?**

**A:** Currently, Hop3 stores backups locally on the server in `/var/hop3/backups/`. Remote storage support (S3, Backblaze B2, etc.) is planned for a future release. In the meantime, you can manually copy backups to remote storage using standard tools like `rsync`, `s3cmd`, or `rclone`.

**Q: Are backups encrypted?**

**A:** Currently, backups are stored unencrypted on the server with restricted file permissions (600/700) to prevent unauthorized access. Backup files contain environment variables which may include sensitive data like API keys and passwords, so access to the Hop3 server should be carefully controlled.

Backup encryption is planned for a future release and will use modern encryption tools like `age` or GPG. Until then, ensure your server has appropriate access controls and consider encrypting backup copies manually if you need to store them off-server.

**Q: How often should I backup my applications?**

**A:** The backup frequency depends on how critical your application is and how frequently it changes:

- **Before every deployment**: Always create a backup before deploying new code
- **Production apps**: Daily backups recommended
- **Development/staging apps**: Weekly backups are usually sufficient
- **Before major changes**: Always backup before database migrations, configuration changes, or system updates

You can automate backups using cron jobs or CI/CD pipelines. Scheduled backups with retention policies will be built into Hop3 in a future release.

**Q: How long are backups retained?**

**A:** Currently, backups are retained indefinitely until you manually delete them with `hop3 backup:delete <backup-id>`. You should establish a retention policy based on your needs:

- Critical applications: Keep 30+ days of backups
- Standard applications: Keep 7-14 days
- Development: Keep 3-7 days

Automatic retention policies will be available in a future release, allowing you to configure automatic cleanup of old backups.

**Q: Can I use backups to clone an application?**

**A:** Yes! Backups can be restored to a different application name, effectively cloning your application:

```bash
hop3 backup:restore <backup-id> --target-app <new-app-name>
```

This creates a completely independent copy of the application, which is useful for creating staging environments, testing changes, or migrating applications.

**Q: What happens if a backup becomes corrupted?**

**A:** Hop3 backups use SHA256 checksums to detect corruption. When you try to restore a corrupted backup, Hop3 will:

1. Verify all checksums before starting the restore
2. If any checksum doesn't match, the restore will fail with a clear error message
3. No partial restore will occur - your application remains unchanged

If a backup is corrupted:
- Use a different, uncorrupted backup
- Investigate how the corruption occurred (disk failure, etc.)
- Create a new backup from the current application state

You can manually verify backup integrity at any time with `hop3 backup:info <backup-id>`, which checks all checksums.

**Q: How much disk space do backups use?**

**A:** Backup size depends on your application:

- Compressed source code: Usually 10-50% of the git repository size
- Compressed data files: Usually 30-70% of the original size (varies by file type)
- Database dumps: Similar size to the database (text format SQL)
- Env variables: Negligible (a few KB)

As a rule of thumb, plan for backups to use 50-80% of your total application size. Monitor `/var/hop3/backups/` disk usage and delete old backups when needed.

**Q: Can I restore a backup from an older version of Hop3?**

**A:** Backups include the Hop3 version that created them. Generally:

- **Same version**: Fully compatible
- **Newer Hop3 version**: Usually compatible (backward compatibility maintained)
- **Older Hop3 version**: May require manual intervention

Hop3 will warn you if there are compatibility concerns during restore. Always test restores in a non-production environment first if you're concerned about version differences.

## Troubleshooting

**Q: My deployment failed. How do I see what went wrong?**

**A:** Hop3 provides several ways to debug deployment issues:

1. **View build logs during deployment** - Use the `-v` (verbose) or `--debug` flag:
   ```bash
   hop3 deploy myapp -v       # Show Docker build output
   hop3 deploy myapp --debug  # Maximum verbosity
   ```

2. **View stored build logs after deployment** - Build logs are saved automatically:
   ```bash
   hop3 app:build-logs myapp
   ```

3. **Check application logs** - For runtime errors after successful builds:
   ```bash
   hop3 app:logs myapp
   ```

4. **Check server logs** - For persistent debugging information, check `/home/hop3/log/server.log` on the server.

**Q: My Docker-based app returns 502 Bad Gateway. How do I debug this?**

**A:** A 502 error typically means nginx can't connect to your application. Here's how to diagnose:

1. **Check the build succeeded** - View build logs to ensure the image was created:
   ```bash
   hop3 app:build-logs myapp
   ```

2. **Check the container is running** - Verify the container started:
   ```bash
   hop3 app:status myapp
   ```

3. **Check application logs** - Look for startup errors:
   ```bash
   hop3 app:logs myapp
   ```

4. **Verify the port** - Ensure your app listens on the correct port (usually 8080 for Docker apps).

5. **Test locally first** - Build and run your Docker image locally to verify it works:
   ```bash
   docker build -t myapp .
   docker run -p 8080:8080 myapp
   curl http://localhost:8080
   ```

**Q: How do I see detailed output when running demos?**

**A:** The demo launcher supports verbose and debug modes:

```bash
# Normal mode - standard output
python demos/demo.py --host HOST demo1

# Verbose mode - shows Docker build output
python demos/demo.py --host HOST -v demo1

# Debug mode - maximum verbosity
python demos/demo.py --host HOST --debug demo1
```

In verbose/debug mode, hop3 commands will show Docker build progress, container logs, and detailed error messages.
