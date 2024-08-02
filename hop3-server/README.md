# hop3-server

This subproject provides (or will provide) API endpoints for the hop3 CLI (implemented in the `hop3-cli` subproject).

It currently uses the `RPyC` RPC framework, which is a robust and easy-to-use way to expose Python objects and functions over a network. This may be replaced with a more standard REST API in the future, or by something ad-hoc.


## Implementation Status

[x] = done
[.] = in progress
[ ] = not done

[x] apps              List apps
[ ] build             Build app but don't deploy it
[ ] backup            Backup/restore app data
[ ] config            Show/manage config for current app
[ ] deploy            Deploy app
[ ] destroy           Destroy app
[ ] help              Display help
[ ] init              Create a new app
[ ] logs              Tail running logs
[ ] restart           Restart an app
[ ] run               Run a command in the app's environment
[ ] scale             Scale processes
[ ] server            Manage the Hop3 server
[ ] start             Start an app
[ ] status            Show app status
[ ] stop              Stop an app
[.] system            Show system info
[ ] update            Update an app
[ ] version           Show Hop3 version
