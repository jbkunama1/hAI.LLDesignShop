# MCP Server Instructions

Guidelines for Model Context Protocol (MCP) servers integrated with this repository:

1. **Environment Setup**:
   - Ensure required environment variables (e.g., database URIs, API tokens) are securely injected.
2. **Tool Scope**:
   - Restrict file access and database operations strictly to the designated project directories (`telegram-bot/`, `evershop/`, etc.).
3. **Error Handling & Logging**:
   - Catch exceptions gracefully and log structured errors without leaking sensitive data (such as bot tokens or user chats).
