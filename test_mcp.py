"""MCP 冒烟测试: 通过 stdio 拉起服务并调用各工具。"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def cookie_header() -> str:
    jar = json.loads(open(".session.json", encoding="utf-8").read())
    return "; ".join(f"{c['name']}={c['value']}" for c in jar["cookies"])


async def main():
    params = StdioServerParameters(
        command=sys.executable, args=["mcp_server.py"], cwd=".")
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("工具:", [t.name for t in tools.tools])

            res = await s.call_tool("list_features", {})
            feats = json.loads(res.content[0].text)["功能"]
            print(f"功能数: {len(feats)}")

            for f in feats:
                res = await s.call_tool("query_info", {"feature": f})
                d = json.loads(res.content[0].text)
                stats = {k: v for k, v in d.items()
                         if isinstance(v, int) and k != "ok"}
                print(f"  {f:<22} ok={d.get('ok')} {stats}")


asyncio.run(main())
