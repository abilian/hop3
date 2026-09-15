# FAQ

**Q: Why "Hop3"?**

**A:** "Hop3" means "hop cubed" or "hop to the power of 3", or "hop, hop, hop!", which in French means "hurry up!". The name also nods to the third iteration of a similar system we've been developing and using for years (Abilian Cloud Controller -> Nua -> Hop3).

**Q: What makes Hop3 different from other PaaS offerings?**

**A:** Hop3 sets itself apart by combining simplicity, modularity, and a commitment to open-source principles. Many PaaS solutions are proprietary, or lean on complex, resource-intensive containerization and orchestration tools such as Docker and Kubernetes. Hop3 is designed to be lightweight and accessible, and runs efficiently even on low-end devices and in resource-constrained environments.

Hop3 is extensible and customizable through a plugin-oriented architecture. Such modularity is rare in the PaaS space, where platforms often trade customizability for simplicity. With plugins, users can tailor the platform to their needs, extending its functionality without bloating the core.

Hop3's open-source nature makes it easy to tailor or enhance the platform, share knowledge, and develop new features. Commercial PaaS offerings impose the limitations and costs of proprietary technologies, and their users have no influence over how the platform develops.

Hop3 prioritizes direct integration with the host system, which improves performance and resource use compared with solutions that abstract away the underlying infrastructure. The direct approach also enhances security and reliability, since users keep closer control over their deployment environments.

Finally, Hop3 avoids the complexity and overhead of larger platforms like Kubernetes. It aims for a straightforward deployment experience, which appeals to small and medium-sized projects, early-stage startups, and developers who want an agile, cost-effective way to deploy and manage their applications without giving up the power and flexibility of larger PaaS solutions.

**Q: Why Python? / why not Go/Rust/Erlang/...?**

**A:** Python was chosen for its simplicity, readability, and large ecosystem, which make the platform accessible to a broad range of developers.

Go, Rust, and Erlang have their own advantages, including performance and concurrency support, but Python balances performance, ease of development, and community support, and it is the language we know best.

**Q: Can Hop3 support applications built with various programming languages?**

**A:** Yes. Hop3 is language-agnostic: developers can deploy applications written in Python, JavaScript (Node.js), Ruby, Java, and more. The underlying infrastructure and tooling accommodate the needs of modern web applications, so developers can use their preferred languages and frameworks without compatibility concerns.

**Q: Why not just use Dokku?**

**A:** Dokku was the original "self-hosted and lightweight Heroku-clone", but it has architectural limitations: it can be heavy for small-scale deployments or low-end hardware, and its customization options are limited by its reliance on Docker. Hop3 is leaner, with better performance and security, and its modular, plugin-oriented design is more flexible and extensible.

**Q: Why not just use Piku or Sailor?**

**A:** Both Piku and Sailor are good solutions. Hop3 aims to offer broader functionality, a more polished user experience, and support for more deployment contexts. We share roots with Piku and Sailor, including some shared code, but Hop3's architecture is more openly extensible, which encourages use of and contribution to its ecosystem, especially through plugins.

**Q: Why not use Docker or a similar container-based technology?**

**A:** Docker is complex and demands many system resources, particularly for smaller projects or devices with limited capabilities. Hop3 keeps deployment straightforward and integrates more deeply with the host and external services, which improves performance and resource use.

**Q: Why not use Kubernetes?**

**A:** Kubernetes, despite its scalability and robustness, often brings unnecessary complexity and overhead to simpler applications and smaller-scale deployments. Hop3 targets those who want a more accessible, less cumbersome solution, avoiding the steep learning curve and extensive setup that Kubernetes requires, and offering a simpler path to deploying applications.

**Q: Why not use Heroku?**

**A:** Heroku is easy to use and developer-friendly, but it comes at a cost, both in money and in flexibility and control. Hop3 is a more cost-effective, adaptable alternative that still supports a broad range of deployment scenarios. By fostering an open, plugin-enhanced ecosystem, Hop3 offers a level of customization and community engagement that Heroku cannot match, without proprietary lock-in.

**Q: Why not use platforms like Render, Vercel, Netlify, etc.?**

**A:** Platforms such as Render, Vercel, and Netlify provide valuable services, but often with less flexibility and control, and at a higher price. Hop3 is more versatile and economical, with broader deployment capabilities and deeper customization. It is also open source, so users are not locked into proprietary ecosystems, and its openness encourages collaboration and gives users a level of control over their deployment environments that proprietary platforms cannot match.

**Q: How does Hop3 contribute to environmental sustainability?**

**A:** Hop3 contributes to environmental sustainability by optimizing resource use and encouraging green computing practices. Through efficient coding, resource allocation, and energy-efficient technologies, it minimizes the carbon footprint of hosting and running web applications. It also provides developers with tools and guidelines for sustainable app development, which reduces electronic waste and encourages the use of renewable energy in cloud computing.

**Q: Why did Hop3 choose uWSGI for application deployment?**

**A:** We chose [uWSGI](https://uwsgi-docs.readthedocs.io/) in [emperor mode](https://uwsgi-docs.readthedocs.io/en/latest/Emperor.html) because its feature set aligns with our objectives of simplicity, performance, and security.

1. uWSGI integrates cleanly with Python WSGI applications and `virtualenvs`, which suits Python-based projects, a large portion of web applications today. This simplifies deployment: developers focus on their application logic, and they build and ship their applications faster as a result.

1. uWSGI provides process management features, including monitoring, restarting, and basic resource limiting. These capabilities keep applications responsive and stable under varying loads, which removes the need for manual intervention and contributes to a better overall user experience.

While uWSGI has served Hop3 well, future versions will offer alternatives (as plugins) to accommodate a broader range of use cases and technologies. Potential alternatives are listed in the [uWSGI chapter of the abilian books](https://github.com/abilian/books/blob/main/uwsgi/chap-9-2.md), along with the criteria we use to compare them.

For more notes about uWSGI, see <https://github.com/abilian/books/blob/main/uwsgi/README.md>.

## Troubleshooting

For troubleshooting, see the **[Troubleshooting Guide](troubleshooting.md)**.

**Q: My deployment failed. How do I see what went wrong?**

**A:** Use verbose mode and check logs:

```bash
hop3 deploy --app myapp -v          # Verbose output during deploy
hop3 app build-logs --app myapp     # View build logs after deploy
hop3 app logs --app myapp           # View runtime logs
```

See [Deployment Issues](troubleshooting.md#deployment-issues) for detailed diagnosis steps.

**Q: My app returns 502 Bad Gateway. How do I debug this?**

**A:** Check that your app is running and listening on the correct port:

```bash
hop3 app status --app myapp   # Check app state
hop3 app logs --app myapp     # Look for startup errors
```

See [502 Bad Gateway](troubleshooting.md#502-bad-gateway) in the Troubleshooting Guide for common causes and solutions.

**Q: How do I see detailed output when deploying?**

**A:** Use the `-v` (verbose) or `--debug` flags:

```bash
hop3 deploy --app myapp -v          # Verbose mode
hop3 deploy --app myapp --debug     # Maximum verbosity
```

