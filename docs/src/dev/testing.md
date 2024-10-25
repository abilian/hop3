# Testing Hop3

## Unit Testing

Each subproject in Hop3 has its own unit tests. These tests are run using the `pytest` framework. To run the tests, navigate to the root directory of the subproject and run the following command:

```bash
pytest
# or
make test
```

To run all the tests from the root directory of the project, run the following command:

```bash
nox
```

## End-to-End Testing

We have developped a specific framework to test the end-to-end functionalities of Hop3.

First you have to have a server or VM which you can access thourgh SSH. While it should eventually be possible to use a local VM, we currently only support remote servers.

The adress of the server should be set using the `HOP3_DEV_HOST` environment variable, for instance by setting a proper value in your `.envrc` file (if you are using `direnv`).

To run the end-to-end tests, navigate to the root directory of the project and run the following command:

```bash
make test-e2e
```

## Contiuous Integration

We are using `SourceHut` for our CI/CD pipeline. The configuration is stored in the `.builds` directory. The pipeline is triggered on each push to the `main` branch, but there is currently a delay because Sourcehut is currently set up as a GitHub mirror.

See: <https://builds.sr.ht/~sfermigier/hop3/> for the current build status.

Note that End-to-End tests are currently not run in the CI pipeline, as they require a specific setup.
