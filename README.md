# Example MCP Server with FastMCP (Python)

## Overview

This repository provides an educational example of a Model Context Protocol (MCP) server implemented in Python using the [FastMCP](https://github.com/modelcontextprotocol/fastmcp) library. It demonstrates how to expose tools, resources, and prompts to AI clients, enabling seamless integration with applications like IDEs, chatbots, and agent frameworks.


## What is MCP?

Model Context Protocol (MCP) is an open protocol that standardizes how AI applications connect to external tools and data sources. MCP servers expose:

- **Tools:** Executable functions that can be called by AI clients
- **Resources:** Data sources for context (files, APIs, etc.)
- **Prompts:** Reusable templates for interactions

Learn more: [modelcontextprotocol.io](https://modelcontextprotocol.io/)


## Why FastMCP?

[FastMCP](https://github.com/modelcontextprotocol/fastmcp) is a Python library for building MCP servers quickly and easily. It provides:

- Simple API for defining tools, resources, and prompts
- Support for stdio and HTTP transports
- Type-safe schemas for tool inputs/outputs
- Integration with popular Python frameworks


## How does MCP work?

MCP uses a client-server architecture:

- **Host:** The AI application (e.g., VS Code, Claude Desktop)
- **Client:** Connects to one or more MCP servers
- **Server:** Exposes tools, resources, and prompts

Servers declare their capabilities during initialization. Tools are listed and can be invoked by the client or model. FastMCP makes it easy to implement these features in Python.


## Example Features

- Define Python functions as MCP tools
- Expose resources (e.g., files, API data)
- Add prompts for structured interactions
- Support for both stdio and HTTP transports


## Usage

1. Install FastMCP:
	```bash
	pip install fastmcp
	```
2. Run the example server:
	```bash
	python mcp_server.py
	```
3. Connect an MCP-compatible client (e.g., Claude Desktop, VS Code, etc.) to the server.

See `mcp_server.py` for example code.


## References

- [MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18/index)
- [FastMCP Python Library](https://github.com/modelcontextprotocol/fastmcp)
- [Example Servers](https://modelcontextprotocol.io/examples)

---
**Note:** This example is for educational purposes. Always review server code and tool definitions before connecting to any AI application.
