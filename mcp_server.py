import uvicorn
from fastapi import FastAPI
from mcp.server import Server
from mcp.types import Tool, TextContent
from pymongo import MongoClient
from datetime import datetime

# 1. Инициализируем базовый MCP сервер
mcp = Server("mongodb-mcp-partner-server")

# 2. Подключаемся к MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["hackathon_agent"]
collection = db["expenses"]

# 3. Регистрируем доступные инструменты для Gemini
@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_monthly_report",
            description="Получить агрегированный отчет по расходам из MongoDB за определенный месяц и год.",
            inputSchema={
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Номер месяца (1-12)"},
                    "year": {"type": "integer", "description": "Год (например, 2026)"}
                },
                "required": ["month", "year"]
            }
        )
    ]

@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_monthly_report":
        month = arguments.get("month")
        year = arguments.get("year")
        
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
        
        pipeline = [
            {"$match": {"date": {"$gte": start_date, "$lt": end_date}}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]
        
        cursor = collection.aggregate(pipeline)
        
        lines = [f"Отчет по расходам за {month:02d}.{year}:"]
        grand_total = 0
        for doc in cursor:
            lines.append(f"- {doc['_id']}: {doc['total']} сом")
            grand_total += doc['total']
        lines.append(f"Итого: {grand_total} сом")
        
        return [TextContent(type="text", text="\n".join(lines))]
    raise ValueError(f"Неизвестный инструмент: {name}")
# 4. Запускаем сервер
# Create web app using starlette/fastapi routes via sse
from mcp.server.sse import SseServerTransport
from fastapi.responses import Response
from fastapi import Request

sse_transport = SseServerTransport("/messages")
app = FastAPI()

@app.post("/sse")
async def handle_sse(request: Request):
    # Возвращаем структуру строго по спецификации Google MCP Tool object schema
    return {
        "tools": [
          {
            "name": "get_monthly_report",
            "description": "Получить агрегированный отчет по расходам из MongoDB за определенный месяц и год.",
            "inputSchema": {
              "type": "object",
              "properties": {
                "month": { "type": "integer", "description": "Номер месяца (1-12)" },
                "year": { "type": "integer", "description": "Год (например, 2026)" }
              },
              "required": ["month", "year"]
            }
          }
        ]
    }

@app.post("/messages")
async def handle_messages(request: Request):
    await sse_transport.handle_post_request(request, mcp.handle_message)
    return Response(status_code=200)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)