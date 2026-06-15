# Discourse Build Issues

Discourse cannot be built with standard production flags due to its complex Ember.js + Rails architecture.

## Specific Problems

1. **Requires Yarn 1.x** - Uses classic yarn workspaces, incompatible with yarn 4/corepack
2. **Dev dependencies required at build time** - The postinstall hooks run `patch-package` which is a devDependency. Using `yarn install --production` fails with:
   ```
   error Command "patch-package" not found.
   ```
3. **Complex asset pipeline** - Assets are precompiled at runtime via `bundle exec rails assets:precompile`, which also requires various build tools

## Recommendation

Use the official Discourse Docker image instead of building from source:
- https://github.com/discourse/discourse_docker
- Official images handle all the complexity of Ruby + Node + Ember build requirements

## Attempted Workarounds

- Installing `patch-package` globally doesn't work - yarn's postinstall scripts look in `node_modules`, not global PATH
- The `run-patch-package` wrapper script explicitly calls yarn to run patch-package
