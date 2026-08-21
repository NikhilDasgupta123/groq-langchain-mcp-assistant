from mcp.server.fastmcp import FastMCP

from mcp_server.tools.calculator import register_calculator_tools
from mcp_server.tools.browser import register_browser_tools


mcp = FastMCP("MCP AI Assistant Server")

register_calculator_tools(mcp)
register_browser_tools(mcp)


if __name__ == "__main__":
    mcp.run(transport="stdio")
