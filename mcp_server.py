from mcp.server.fastmcp import FastMCP

# Create the FastMCP server instance
mcp = FastMCP("mcp-documentation-server")

# Register the tool using FastMCP decorator
@mcp.tool()
def get_documentation_from_database() -> dict:
    """
    Return mocked documentation records from a documentation database.
    This is useful for testing MCP tool calls without a real database.
    """
    return {
        "database": "documentation_db",
        "record_count": 3,
        "documents": [
            {
                "id": "doc-001",
                "title": "How to Use MCP Servers",
                "summary": "An overview of MCP servers, tools, and resources for AI agents.",
                "category": "getting-started",
                "source": "mocked_database",
            },
            {
                "id": "doc-002",
                "title": "Configuring an MCP Client",
                "summary": "Example configuration for connecting clients to local MCP servers.",
                "category": "configuration",
                "source": "mocked_database",
            },
            {
                "id": "doc-003",
                "title": "Best Practices for Tool Design",
                "summary": "Guidance on designing clear, safe, and useful tools for AI agents.",
                "category": "best-practices",
                "source": "mocked_database",
            },
        ],
    }


if __name__ == "__main__":
    mcp.run("stdio")
