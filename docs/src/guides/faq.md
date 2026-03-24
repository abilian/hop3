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

For comprehensive backup documentation, see the **[Backup and Restore Guide](backup-restore.md)**.

**Q: How do I backup and restore my applications?**

**A:** Use the backup commands:

```bash
# Create backup
hop3 backup:create <app-name>

# List backups
hop3 backup:list <app-name>

# Restore from backup
hop3 backup:restore <backup-id>
hop3 app:restart <app-name>
```

Backups include source code, data, environment variables, and attached services. See the [Backup and Restore Guide](backup-restore.md) for complete details.

**Q: Can I clone an application using backups?**

**A:** Yes, restore to a different app name:

```bash
hop3 backup:restore <backup-id> --target-app <new-app-name>
```

**Q: Is remote storage or encryption supported?**

**A:** Currently backups are stored locally in `/var/hop3/backups/` without encryption. Remote storage (S3, B2) and encryption are planned for future releases. For now, use tools like `rsync` or `rclone` for off-server copies.

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
