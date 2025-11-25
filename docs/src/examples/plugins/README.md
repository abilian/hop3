# Plugin Examples

This directory contains example plugins demonstrating various aspects of the Hop3 plugin system.

## Available Examples

### [example-builder](example-builder/)

A minimal build strategy plugin that demonstrates:
- Plugin structure and registration
- BuildStrategy protocol implementation
- Hook implementation (`get_build_strategies()`)
- Error handling and logging
- Build artifact creation

**Use this example to learn**:
- Basic plugin development workflow
- How to implement the `accept()` and `build()` methods
- How to return `BuildArtifact` information
- Best practices for build strategies

## Using These Examples

### As Learning Tools

1. **Read the code**: Each example is heavily commented to explain key concepts
2. **Study the structure**: Note how files are organized and named
3. **Check the README**: Each example has a README explaining what it does
4. **Test locally**: Try running the examples with test applications

### As Templates

1. **Copy the example**: Start with the example closest to your needs
2. **Rename files and classes**: Update to match your plugin's purpose
3. **Modify the logic**: Implement your specific functionality
4. **Test thoroughly**: Ensure your plugin works with real applications
5. **Package it**: Follow the [External Plugin Guide](../../dev/external-plugins.md)

## Example Structure

Each example follows this structure:

```
example-name/
├── README.md          # What this example demonstrates
├── plugin.py          # Plugin class with hook implementations
└── builder.py         # Strategy implementation (builder, deployer, service, etc.)
```

For external plugins, you would add:

```
example-name/
├── pyproject.toml     # Package metadata and entry points
├── LICENSE            # License file (Apache 2.0 recommended)
├── src/
│   └── example_name/
│       ├── __init__.py
│       ├── plugin.py
│       └── builder.py
└── tests/
    ├── test_plugin.py
    └── test_builder.py
```

## Testing Examples

To test an example plugin:

```bash
# Navigate to example directory
cd example-builder

# Run Python to check imports
python3 -c "from plugin import plugin; print(plugin.name)"

# Test with hop3 (if installed)
python3 -c "from hop3.core.plugins import get_plugin_manager; pm = get_plugin_manager(); print([p.name for name, p in pm.list_name_plugin()])"
```

## More Examples

Want to see more examples? Check:

- **Real implementations** in `packages/hop3-server/src/hop3/plugins/`
  - `postgresql/` - Service strategy example
  - `docker/` - Build and deployment strategies
  - `proxy/nginx/` - Proxy strategy example
- **Builder implementations** in `packages/hop3-server/src/hop3/builders/`
  - `python.py` - Production Python builder
  - `node.py` - Node.js builder
  - `static.py` - Static file builder

## Contributing Examples

Have a useful example to share? Contributions are welcome!

1. Create your example following the structure above
2. Document it thoroughly with comments and README
3. Test it with real applications
4. Submit a pull request

## See Also

- [Plugin Development Guide](../../dev/plugin-development.md) - Comprehensive plugin guide
- [Protocol Reference](../../dev/protocol-reference.md) - Strategy protocol specifications
- [Hook Specifications](../../dev/hook-specifications.md) - Available hooks
- [External Plugin Guide](../../dev/external-plugins.md) - Publishing plugins
