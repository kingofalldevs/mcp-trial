from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test")
if hasattr(mcp, "_app"):
    print("mcp._app exists!")
    print(type(mcp._app))
else:
    print("mcp._app does not exist")
