import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server(
  {
    name: "simple-json-server",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "get_json_data",
        description: "Returns a mock JSON dataset representing user info and system status.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name === "get_json_data") {
    const data = {
      status: "success",
      timestamp: new Date().toISOString(),
      serverInfo: {
        name: "simple-json-server",
        type: "Model Context Protocol (MCP)",
        status: "online",
        environment: "Node.js"
      },
      payload: {
        users: [
          { id: 101, name: "Sarah Connor", role: "Leader" },
          { id: 102, name: "John Connor", role: "Commander" },
          { id: 103, name: "T-800", role: "Guardian" }
        ],
        config: {
          debug: true,
          mode: "autonomous",
          location: "Los Angeles"
        }
      }
    };

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(data, null, 2),
        },
      ],
    };
  }
  throw new Error(`Unknown tool: ${request.params.name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("Simple JSON MCP server running on stdio");
