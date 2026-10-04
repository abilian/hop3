# Flask email addon round-trip

Sends a message through the Hop3 email addon's loopback relay and finds it in the catch backend's sink (Mailpit), proving the path end to end: the injected `SMTP_*` variables, Postfix on `127.0.0.1:25`, and the `catch` backend.
