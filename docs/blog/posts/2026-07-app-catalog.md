---
date: 2026-07-24
template: blog_post.html
description: "Hop3's app catalog lets you browse real self-hosted applications in the dashboard and install one without reading its setup guide: an admin account is created for you and a sign-in is verified before the deploy reports success."
tags:
  - Announcement
  - Operations
  - Getting Started
---

# Nextcloud, Without the Install Guide

Nextcloud's installation documentation is thorough, well written, and roughly a morning's work. You need a database and a user for it. You need a specific set of PHP extensions, and a `php.ini` with a memory limit and an upload size that are not the defaults. You need a reverse proxy that sets the right headers, or the app will build every URL wrong and the login will loop. You need a cron job, or background jobs quietly stop. You need a TLS certificate. Then you get to create the admin account.

None of that is Nextcloud being difficult. Every serious self-hosted application has a version of that list, which is why so many people who want to self-host end up not self-hosting.

Hop3 0.7 ships an **app catalog**. You open the dashboard, find the app, and install it.

## What that looks like

The catalog is a section of the Hop3 web dashboard. It lists applications with a description, an icon, and what they need. You pick one, give it a name and a domain, and press install.

Hop3 then does the list above. It provisions the database and the cache the app declares and injects the connection details. It installs the runtime and the extensions. It configures the reverse proxy, including the headers that make an app behind a proxy build correct URLs. That is the single most common way a self-hosted install ends up broken in a way that looks like the app's fault. It requests a certificate. It runs the application's own first-run bootstrap, **generates an admin credential and stores it**, and starts the app.

Then it signs in, to check.

When the deploy reports success, you go to `hop3 app credentials`, take the generated password, and log in. There is no setup wizard waiting for you and no configuration file to edit first.

The applications in the catalog are real ones people actually run: Nextcloud, WordPress, Forgejo and Gitea, Matomo, BookStack, Mattermost, Keycloak, Vikunja, Kanboard, Miniflux, Dolibarr, Invoice Ninja, LimeSurvey, Radicale, Uptime Kuma, Paheko, Bugsink, Isso, Easy!Appointments. The set grows; it is not meant to be a fixed list.

## Why you can trust it

It started with an application that passed every check we had while being unusable.

**Bugsink** is an error tracker. It deployed cleanly. It returned HTTP 200. Its login page rendered. Every automated validation was green, and we advertised it as working.

It threw a 500 the moment anyone actually signed in. Bugsink runs two processes, a web app and a background worker with its own separate queue database, and the second one was never wired up. Everything before the login worked. Everything after it did not.

The lesson generalises past that one app. A status code tells you a web server answered. Behind a 200 can sit a placeholder page, a generic error page, a maintenance notice, or another app's content served through a misconfigured vhost. We had been treating "the port responds" as "the app runs", and those are different claims.

So the bar moved. **Every application in the catalog ships a smoke test that signs in through the app's own authentication**, using the credential Hop3 generated, and confirms that a wrong password is refused. A login form that accepts anything is not a passing test, and without checking it you cannot distinguish a working sign-in from a broken one that happens to redirect.

The check is required in order to publish to the catalog. It runs at the end of **every** deploy, including deploys started from the dashboard, and on demand:

```bash
hop3 app check --app myapp
```

An app that no longer signs in is a failed deploy.

## Verification that survives you

There is an obvious problem with a platform holding an app's admin password: you are going to change it. You should change it. And then the smoke test is signing in with a credential that no longer works, and starts failing for a reason that has nothing to do with the app.

So an application can declare a **probe account**, a separate, non-privileged account that Hop3 owns and whose password Hop3 rotates:

```toml
[probe]
username = "hop3-probe"
```

The check signs in as the probe. You own the admin account and can do what you like with it. Applications where a second account makes no sense simply omit the section.

## Signed, not merely downloaded

The catalog is content fetched from a network, which makes it a supply chain. It is **signed**, and Hop3 verifies the signature before trusting anything in it ([ADR 049](/developers/adrs/049-catalog-distribution/)). The dashboard treats catalog content as untrusted regardless: application descriptions are sanitised before rendering and only raster icons are accepted, so a catalog entry cannot inject markup into the page an operator is looking at.

## What it took to get here

Every one of the catalog applications was installed by hand, one at a time, through the dashboard, by someone reporting what a first-time operator actually sees. Every failure was traced to a platform defect and fixed in the platform itself.

- **HTTPS is now the default.** Plain HTTP redirects. Three applications could not be logged into at all over the HTTP vhost, because they set `Secure` cookies, the browser correctly declined to send them back, and the login silently looped. That looks exactly like a wrong password.
- **PHP's built-in server got more than one worker.** It is single-threaded, so any application that makes a request to itself while installing deadlocks against its own only worker. Nextcloud's installer does exactly this. Ten of the catalog apps sit on that runtime.
- **A failed install can be retried.** Installing from the catalog recorded the app before deploying it, so a failed deploy left an app that could be neither used nor reinstalled: every retry refused with "already exists".
- **`hop3 app credentials` stopped showing passwords for accounts that were never created.** The credential is generated up front; if the application's own bootstrap then failed, the password was still presented as though it worked.

Each of those would have hit a real operator. Packaging applications is how we find them. The apps are the instrument; a defect that only shows up in real software is why we use real software.

## From the CLI

Everything above works from the command line too, if you would rather script it:

```bash
hop3 catalog list
hop3 catalog install nextcloud --app cloud --domain cloud.example.com
```

The dashboard is the primary way in, and the CLI is the same operation for people who prefer a terminal.

---

*Design records: [ADR 049](/developers/adrs/049-catalog-distribution/) for catalog distribution and signing, [ADR 056](/developers/adrs/056-app-admin-credentials/) for generated admin credentials. Getting started: the [app catalog guide](/guides/app-catalog/).*
